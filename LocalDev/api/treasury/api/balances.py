"""Member balance HTTP surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.treasury.auth import TREASURY_READ
from api.treasury.db.session import get_treasury_db
from api.treasury.services import balance as svc

router = APIRouter()


@router.get("/members/{member_id}/balance")
async def get_member_balance(member_id: str, user=Depends(get_current_user)):
    """A member's cached balance.

    Access: the member themself, OR any `treasury:read` holder IN THE SAME CHAPTER.
    A non-existent member, or one outside the requester's chapter, returns 404 so
    cross-chapter existence is never leaked. Mirrors the /statement guard exactly —
    the previous `role == "officer"` check both bypassed the capability model and
    let an officer read balances in *other* chapters (tenant-integrity gap).
    """
    sb = get_treasury_db()

    if str(user["id"]) != str(member_id):
        grant = (
            sb.table("treasury_grants")
            .select("id")
            .eq("chapter_id", user["chapter_id"])
            .eq("member_id", user["id"])
            .eq("capability", TREASURY_READ)
            .maybe_single()
            .execute()
        ).data
        if not grant:
            raise HTTPException(403, f"Missing Treasury capability: {TREASURY_READ}")

    member = (
        sb.table("members")
        .select("chapter_id")
        .eq("id", member_id)
        .maybe_single()
        .execute()
    ).data
    if not member or str(member["chapter_id"]) != str(user["chapter_id"]):
        raise HTTPException(404, "Member not found")

    return svc.get_member_balance(sb, member_id=member_id)
