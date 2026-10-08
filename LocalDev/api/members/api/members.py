from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from api.rbac.core.policy import LEGACY_ROLE_COMPAT
from api.rbac.services.permissions import has_permission
from api.platform.db import get_db
from api.platform.rpc import call_rpc
from api.sms_consent import CONSENT_COLUMNS, has_consent

ROLES_ASSIGN = "roles:assign"
# Who may see another member's SMS consent — the same key that gates inviting.
MEMBERS_INVITE = "members:invite"

# Roster statuses. 'invited' (0148) is a real roster entry — a member who has
# been invited but has not yet redeemed a setup code. Excluding it made every
# invitee invisible to the officer who had just invited them.
ROSTER_STATUSES = ["active", "invited"]

router = APIRouter()


@router.get("/")
def list_members(user=Depends(get_current_user)):
    """List the chapter roster: active members plus pending invitees.

    `sms_consent` rides along (#57) so officers can see who is textable and a
    member can see their own state — the rule itself stays in api/sms_consent.py.
    It is officer-or-yourself data (#88): a caller without `members:invite` gets
    the field on their own row only, never on a teammate's.
    """
    sb = get_db()
    sees_all_consent = has_permission(user, MEMBERS_INVITE, sb=sb)
    result = (
        sb.table("members")
        .select(f"id, name, email, role, status, {CONSENT_COLUMNS}")
        .eq("chapter_id", user["chapter_id"])
        .in_("status", ROSTER_STATUSES)
        .order("name")
        .execute()
    )
    roster = []
    for m in result.data or []:
        row = {
            "id": m["id"],
            "name": m["name"],
            "email": m["email"],
            "role": m["role"],
            "status": m["status"],
        }
        if sees_all_consent or str(m["id"]) == str(user["id"]):
            row["sms_consent"] = has_consent(m)
        roster.append(row)
    return roster


@router.post("/me/sms-consent")
def opt_in_to_sms(user=Depends(get_current_user)):
    """The member opts themselves in to SMS (#57).

    Mounted before the parameterized routes below, which is why it lives here and
    not at the end of the file. Clearing `sms_opted_out_at` is the point: a member
    who texted STOP and later turns the toggle back on is opting back in, and a
    stale opt-out would silently keep them unreachable forever.

    No permission gate — consent is the member's own to give, and it is only ever
    given for themself (`sub` from the token, never a path id).
    """
    sb = get_db()
    now = datetime.now(timezone.utc).isoformat()
    sb.table("members").update(
        {"sms_consent_at": now, "sms_opted_out_at": None}
    ).eq("id", user["id"]).execute()
    return {"sms_consent": True, "sms_consent_at": now}


@router.put("/{member_id}/role")
def update_role(
    member_id: str,
    role: str,
    officer=Depends(require_permission(ROLES_ASSIGN)),
):
    """Promote or demote a member, keeping `members.role` and `member_roles` in step.

    The requested role is validated against the RBAC role catalog (ADR-0003) —
    the catalog is the single source of truth for role names, not a hardcoded
    tuple. The legacy column is narrower than the catalog (its CHECK constraint
    still only accepts 'officer'/'member'), so a catalog role the column cannot
    hold comes back as a 400 rather than a database error; stackable roles are
    assigned through the rbac_assign_role RPC, not here.

    The write itself is the `mem_set_legacy_role` RPC (0154): members.role is
    display-only; permissions come from member_roles via api.rbac. One RPC
    keeps the display column and authoritative role rows atomic.
    """
    sb = get_db()

    known = (
        sb.table("roles").select("key").eq("key", role).maybe_single().execute()
    ).data
    if not known:
        raise HTTPException(400, f"Unknown role: {role}")

    # LEGACY_ROLE_COMPAT's keys ARE the legacy column's domain — the same pair the
    # members_role_check constraint accepts. Checking here keeps the 400 for the
    # one case that deserves it, so every other database failure stays a 500
    # instead of a "bad role" reply carrying raw driver text.
    if role not in LEGACY_ROLE_COMPAT:
        raise HTTPException(
            400, f"Role '{role}' cannot be set on the legacy members.role column"
        )

    try:
        return call_rpc(
            "mem_set_legacy_role",
            {
                "p_chapter_id": officer["chapter_id"],
                "p_member_id": member_id,
                "p_role": role,
                "p_actor_id": officer["id"],
            },
            sb=sb,
        ).data
    except Exception as exc:
        if "is not in chapter" not in str(exc):  # the RPC's tenant guard
            raise
        raise HTTPException(404, "Member not found")
