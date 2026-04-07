from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user, require_officer
from api.db import get_supabase

router = APIRouter()


@router.get("/")
async def list_members(user=Depends(get_current_user)):
    """List all active members in the chapter."""
    sb = get_supabase()
    result = (
        sb.table("members")
        .select("id, name, email, role, status")
        .eq("chapter_id", user["chapter_id"])
        .eq("status", "active")
        .order("name")
        .execute()
    )
    return result.data


@router.put("/{member_id}/role")
async def update_role(member_id: str, role: str, officer=Depends(require_officer)):
    """Change a member's role."""
    if role not in ("officer", "member"):
        raise HTTPException(400, "Role must be 'officer' or 'member'")

    sb = get_supabase()
    result = (
        sb.table("members")
        .update({"role": role})
        .eq("id", member_id)
        .eq("chapter_id", officer["chapter_id"])
        .select("*")
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Member not found")
    return result.data[0]
