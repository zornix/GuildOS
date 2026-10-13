from fastapi import HTTPException, Header, Request

from api.platform.db import get_db


def get_current_user(request: Request, authorization: str = Header(...)):
    """Extract and validate JWT, return member record."""
    token = authorization.replace("Bearer ", "")
    sb = get_db()

    try:
        auth_response = sb.auth.get_user(token)
        auth_user = auth_response.user
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

    member_id = str(auth_user.id)

    # `sub` is members.id — we mint every token ourselves (api/platform/postgres.py).
    result = (
        sb.table("members")
        .select("*, chapters(*)")
        .eq("id", member_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )

    if not result.data:
        raise HTTPException(403, "No active membership found")

    # Session epoch check (0148). Setting a password or issuing a reset code
    # bumps members.token_version, so any token minted before that bump is dead
    # even though its signature and expiry are still valid.
    claims = getattr(auth_user, "claims", None) or {}
    if int(claims.get("ver", 0)) != int(result.data.get("token_version") or 0):
        raise HTTPException(403, "Session no longer valid, please log in again")

    result.data["pwd_setup"] = bool(claims.get("pwd_setup"))
    if result.data["pwd_setup"] and request.url.path not in (
        "/api/auth/set-password", "/api/auth/me",
    ):
        raise HTTPException(403, "PASSWORD_SETUP_REQUIRED")

    return result.data
