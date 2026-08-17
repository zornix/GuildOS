from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import get_current_user
from api.instrumentation.api.schemas import UsageTrack
from api.platform.db import get_db
from api.instrumentation.services import usage as svc
from api.rbac.auth import require_permission

router = APIRouter()


@router.post("/track")
async def track_usage(
    body: UsageTrack,
    user=Depends(get_current_user),
):
    svc.track(
        get_db(),
        chapter_id=user["chapter_id"],
        member_id=user["id"],
        event_name=body.event_name,
        metadata=body.metadata,
    )
    return {"ok": True}


@router.get("/summary")
async def usage_summary(
    days: int = 30,
    user=Depends(require_permission("calendar:officer:view")),
):
    return svc.summary(get_db(), chapter_id=user["chapter_id"], days=days)
