from fastapi import HTTPException, Header

from api.db import get_supabase
from api.config import settings


async def get_current_user(authorization: str = Header(...)):
    """Extract and validate JWT, return member record."""
    token = authorization.replace("Bearer ", "")
    sb = get_supabase()

    try:
        auth_response = sb.auth.get_user(token)
        auth_user = auth_response.user
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    member_id = str(auth_user.id)

    # Demo auth uses member.id as the JWT subject; Supabase auth uses auth_id.
    if settings.use_local_db:
        result = (
            sb.table("members")
            .select("*, chapters(*)")
            .eq("id", member_id)
            .eq("status", "active")
            .maybe_single()
            .execute()
        )
    else:
        result = (
            sb.table("members")
            .select("*, chapters(*)")
            .eq("auth_id", member_id)
            .eq("status", "active")
            .maybe_single()
            .execute()
        )

    if not result.data:
        raise HTTPException(403, "No active membership found")

    # Session epoch check (0148). Setting a password or issuing a reset code
    # bumps members.token_version, so any token minted before that bump is dead
    # even though its signature and expiry are still valid. Only the local path
    # is checked: the Supabase path carries Supabase-issued tokens that have no
    # "ver" claim of ours to compare.
    if settings.use_local_db:
        claims = getattr(auth_user, "claims", None) or {}
        if int(claims.get("ver", 0)) != int(result.data.get("token_version") or 0):
            raise HTTPException(403, "Session no longer valid, please log in again")

    return result.data
