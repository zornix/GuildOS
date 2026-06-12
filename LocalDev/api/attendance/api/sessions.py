"""Attendance sessions HTTP surface. Mounted under `/api/attendance`."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.attendance.api.schemas import SessionCreate
from api.attendance.auth import CHECKIN_CREATE, require_permission
from api.attendance.services import sessions as svc
from api.attendance.services.sessions import get_attendance_db
from api.dependencies import get_current_user

router = APIRouter()


@router.get("/sessions")
async def list_sessions(event_id: str | None = None, user=Depends(get_current_user)):
    return svc.list_sessions(
        get_attendance_db(), chapter_id=user["chapter_id"], event_id=event_id
    )


@router.post("/sessions")
async def create_session(
    body: SessionCreate,
    user=Depends(require_permission(CHECKIN_CREATE)),
):
    return await svc.create_session(
        get_attendance_db(),
        chapter_id=user["chapter_id"],
        event_id=body.event_id,
        mode=body.mode,
        closes_at=body.closes_at.isoformat() if body.closes_at else None,
        actor_id=user["id"],
    )
