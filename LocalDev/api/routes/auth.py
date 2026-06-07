from datetime import datetime, timezone, timedelta

import bcrypt
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user, require_officer
from api.models.schemas import UserProfile, InviteRequest, LoginRequest, SetPasswordRequest
from api.db import get_supabase
from api.config import settings

router = APIRouter()


@router.post("/login")
async def login(body: LoginRequest):
    """
    Authenticate a member or officer.
    Members: email-only login (no password required).
    Officers without a password set: grace login + password_setup_required flag.
    Officers with a password set: email + password required.
    """
    normalized_email = str(body.email).strip().lower()
    sb = get_supabase()
    result = (
        sb.table("members")
        .select("id, name, email, role, chapter_id, password_hash")
        .eq("email", normalized_email)
        .eq("status", "active")
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(401, "No active member found with that email")

    member = result.data

    if member["role"] == "officer" and member.get("password_hash"):
        if not body.password:
            raise HTTPException(403, detail={
                "message": "Password required for officer login",
                "code": "PASSWORD_REQUIRED",
            })
        if not bcrypt.checkpw(
            body.password.encode("utf-8"),
            member["password_hash"].encode("utf-8"),
        ):
            raise HTTPException(401, "Invalid credentials")

    token = pyjwt.encode(
        {"sub": member["id"], "exp": datetime.now(timezone.utc) + timedelta(days=30)},
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    response = {"access_token": token, "token_type": "bearer"}
    if member["role"] == "officer" and not member.get("password_hash"):
        response["password_setup_required"] = True

    return response


@router.post("/set-password")
async def set_password(body: SetPasswordRequest, user=Depends(get_current_user)):
    """Set or change password. Only officers can set passwords."""
    if user["role"] != "officer":
        raise HTTPException(403, "Only officers can set passwords")

    hashed = bcrypt.hashpw(
        body.password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    sb = get_supabase()
    sb.table("members").update({"password_hash": hashed}).eq("id", user["id"]).execute()

    return {"message": "Password set successfully"}


@router.get("/me", response_model=UserProfile)
async def get_me(user=Depends(get_current_user)):
    """Get current user's profile."""
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "chapter_id": user["chapter_id"],
        "chapter_name": (user.get("chapters") or {}).get("name"),
    }


@router.post("/invite")
async def invite_members(body: InviteRequest, officer=Depends(require_officer)):
    """Add new chapter members by email (active, role member). Duplicate emails are reported in failed."""
    sb = get_supabase()
    invited: list[str] = []
    failed: list[dict] = []
    chapter_id = officer["chapter_id"]

    for raw in body.emails:
        email = str(raw).strip().lower()
        local = email.split("@", 1)[0]
        name = local.replace(".", " ").replace("_", " ").strip().title() or "Member"
        try:
            result = sb.table("members").insert({
                "chapter_id": chapter_id,
                "name": name,
                "email": email,
                "role": "member",
                "status": "active",
            }).execute()
            if result.data:
                invited.append(email)
            else:
                failed.append({"email": email, "error": "Insert failed"})
        except Exception as exc:
            failed.append({"email": email, "error": str(exc)})

    return {"invited": invited, "failed": failed}
