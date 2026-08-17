from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.rbac.auth import require_permission
from api.platform.db import get_db

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
    """Change a member's legacy `members.role`.

    The requested role is validated against the RBAC role catalog (ADR-0003) —
    the catalog is the single source of truth for role names, not a hardcoded
    tuple. The legacy column is narrower than the catalog (its CHECK constraint
    still only accepts 'officer'/'member'), so a catalog role the column cannot
    hold comes back as a 400 rather than a database error; stackable roles are
    assigned through the rbac_assign_role RPC, not here.
    """
    sb = get_db()

    known = (
        sb.table("roles").select("key").eq("key", role).maybe_single().execute()
    ).data
    if not known:
        raise HTTPException(400, f"Unknown role: {role}")

    try:
        result = (
            sb.table("members")
            .update({"role": role})
            .eq("id", member_id)
            .eq("chapter_id", officer["chapter_id"])
            .select("id, chapter_id, name, email, phone, role, status, created_at")
            .execute()
        )
    except Exception as exc:  # legacy members.role CHECK constraint
        raise HTTPException(
            400, f"Role '{role}' cannot be set on the legacy members.role column: {exc}"
        )
    if not result.data:
        raise HTTPException(404, "Member not found")
    return result.data[0]
