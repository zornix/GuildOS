from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from api.rbac.core.policy import LEGACY_ROLE_COMPAT
from api.platform.db import get_db
from api.platform.rpc import call_rpc

ROLES_ASSIGN = "roles:assign"

# Roster statuses. 'invited' (0148) is a real roster entry — a member who has
# been invited but has not yet redeemed a setup code. Excluding it made every
# invitee invisible to the officer who had just invited them.
ROSTER_STATUSES = ["active", "invited"]

router = APIRouter()


@router.get("/")
async def list_members(user=Depends(get_current_user)):
    """List the chapter roster: active members plus pending invitees."""
    sb = get_db()
    result = (
        sb.table("members")
        .select("id, name, email, role, status")
        .eq("chapter_id", user["chapter_id"])
        .in_("status", ROSTER_STATUSES)
        .order("name")
        .execute()
    )
    return result.data


@router.put("/{member_id}/role")
async def update_role(
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

    The write itself is the `mem_set_legacy_role` RPC (0154): permissions resolve
    from member_roles unioned with the legacy column, so writing only one of the
    two made demotion revoke nothing. One RPC keeps both sides atomic.
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
