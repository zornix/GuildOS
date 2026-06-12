"""Announcements HTTP surface. Mounted under `/api/announcements` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header

from api.announcements.api.schemas import AnnouncementCreate
from api.announcements.auth import (
    ANNOUNCEMENTS_CREATE,
    ANNOUNCEMENTS_SEND,
    require_permission,
)
from api.announcements.db.session import get_announcements_db
from api.announcements.services import announcements as svc
from api.dependencies import get_current_user

router = APIRouter()


@router.get("/")
async def list_announcements(status: str | None = None, user=Depends(get_current_user)):
    """List chapter announcements. Any authenticated member can view.

    TODO(announcements): members should only see sent announcements whose
    audience includes them; drafts only for announcements:create holders.
    """
    return svc.list_announcements(
        get_announcements_db(), chapter_id=user["chapter_id"], status=status
    )


@router.post("/")
async def create_announcement(
    body: AnnouncementCreate,
    user=Depends(require_permission(ANNOUNCEMENTS_CREATE)),
):
    return svc.create_draft(
        get_announcements_db(),
        chapter_id=user["chapter_id"],
        title=body.title,
        body=body.body,
        audience=body.audience,
        actor_id=user["id"],
    )


@router.post("/{announcement_id}/send")
async def send_announcement(
    announcement_id: str,
    user=Depends(require_permission(ANNOUNCEMENTS_SEND)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return svc.send_announcement(
        get_announcements_db(),
        chapter_id=user["chapter_id"],
        announcement_id=announcement_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )
