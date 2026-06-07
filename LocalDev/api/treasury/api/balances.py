"""Member balance HTTP surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.treasury.db.session import get_treasury_db
from api.treasury.services import balance as svc

router = APIRouter()


@router.get("/members/{member_id}/balance")
async def get_member_balance(member_id: str, user=Depends(get_current_user)):
    # A member may read only their own balance; officers (treasury:read) may read any.
    if user["id"] != member_id and user.get("role") != "officer":
        raise HTTPException(403, "Cannot read another member's balance")
    sb = get_treasury_db()
    return svc.get_member_balance(sb, member_id=member_id)
