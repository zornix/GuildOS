"""Contribution HTTP surface (read-only). Mounted at `/api/contribution`.

`/me` is registered before `/{member_id}` — FastAPI matches in order, and a
parameterized route registered first would swallow the fixed segment.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.contribution.auth import MEMBER_RECORD_VIEW_ANY
from api.contribution.services import record as svc
from api.dependencies import get_current_user
from api.platform.db import get_db
from api.rbac.auth import require_permission

router = APIRouter()


@router.get("/me")
async def my_record(user=Depends(get_current_user)):
    """The signed-in member's own contribution record."""
    return svc.get_record(get_db(), chapter_id=user["chapter_id"], member_id=user["id"])


@router.get("/{member_id}")
async def member_record(
    member_id: str,
    officer=Depends(require_permission(MEMBER_RECORD_VIEW_ANY)),
):
    """Another member's record. Off-chapter reads 404 (no existence leak)."""
    try:
        return svc.get_record(
            get_db(), chapter_id=officer["chapter_id"], member_id=member_id
        )
    except svc.MemberNotFound:
        raise HTTPException(404, "Member not found")
