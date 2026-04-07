from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_user, require_officer
from api.models.schemas import InviteRequest, UserProfile
from api.db import get_supabase, get_supabase_admin
from api.config import settings

router = APIRouter()


class LoginRequest(BaseModel):
    email: str


@router.post("/login")
async def login(body: LoginRequest):
    """
    Demo auth: officer enters email, backend verifies email exists with role=officer.
    Returns a JWT directly — no password, no magic link.
    """
    import jwt as pyjwt

    sb = get_supabase()
    result = (
        sb.table("members")
        .select("id, name, email, role, chapter_id")
        .eq("email", body.email)
        .eq("status", "active")
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(401, "No active member found with that email")

    member = result.data
    if member["role"] != "officer":
        raise HTTPException(403, "Officer access only. Contact your chapter officers.")

    token = pyjwt.encode(
        {"sub": member["id"], "exp": datetime.now(timezone.utc) + timedelta(days=30)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserProfile)
async def get_me(user=Depends(get_current_user)):
    """Get current user's profile."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "chapter_id": user["chapter_id"],
        "chapter_name": user.get("chapters", {}).get("name"),
    }


@router.post("/invite")
async def invite_members(body: InviteRequest, officer=Depends(require_officer)):
    """Bulk invite members via magic link email."""
    sb = get_supabase_admin()
    results = {"invited": [], "failed": []}

    for email in body.emails:
        try:
            sb.auth.admin.invite_user_by_email(str(email))

            sb.table("members").upsert({
                "email": str(email),
                "chapter_id": officer["chapter_id"],
                "name": str(email).split("@")[0],
                "role": "member",
                "status": "active",
            }, on_conflict="email").execute()

            results["invited"].append(str(email))
        except Exception as e:
            results["failed"].append({"email": str(email), "error": str(e)})

    return results
