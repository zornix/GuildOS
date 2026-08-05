"""Announcements HTTP surface. Mounted under `/api/announcements` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from api.announcements.api.schemas import AnnouncementCreate, SmsSendConfirm
from api.announcements.auth import (
    ANNOUNCEMENTS_CREATE,
    ANNOUNCEMENTS_SEND,
    ANNOUNCEMENTS_SEND_SMS,
    require_permission,
)
from api.announcements.db.session import get_announcements_db
from api.announcements.services import announcements as svc
from api.announcements.services import sms as sms_svc
from api.dependencies import get_current_user
from api.rbac.services.permissions import has_permission

router = APIRouter()


@router.get("/")
async def list_announcements(status: str | None = None, user=Depends(get_current_user)):
    """List chapter announcements. Any authenticated member can view.

    Not a 403 surface: members simply get the filtered feed — sent
    announcements whose audience includes them. Drafts (and the `status`
    filter) belong to announcements:create holders.
    """
    sb = get_announcements_db()
    can_manage = has_permission(user, ANNOUNCEMENTS_CREATE)
    return svc.list_announcements(
        sb,
        chapter_id=user["chapter_id"],
        status=status,
        viewer=user,
        include_drafts=can_manage,
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


@router.get("/sms-log")
async def sms_log(
    limit: int = 50,
    user=Depends(require_permission(ANNOUNCEMENTS_SEND)),
):
    """Every SMS send with sender attribution, newest first (exec visibility)."""
    return sms_svc.list_sms_log(
        get_announcements_db(), chapter_id=user["chapter_id"], limit=limit
    )


@router.get("/{announcement_id}/sms-preview")
async def sms_preview(
    announcement_id: str,
    user=Depends(require_permission(ANNOUNCEMENTS_SEND_SMS)),
):
    """Confirmation step: who would the blast reach right now?"""
    try:
        return sms_svc.preview_sms(
            get_announcements_db(),
            chapter_id=user["chapter_id"],
            announcement_id=announcement_id,
        )
    except sms_svc.AnnouncementNotFound:
        raise HTTPException(404, "Announcement not found")


@router.post("/{announcement_id}/send-sms")
async def send_announcement_sms(
    announcement_id: str,
    body: SmsSendConfirm,
    user=Depends(require_permission(ANNOUNCEMENTS_SEND_SMS)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Two-phase confirmed SMS blast. 409 returns the fresh count to re-confirm."""
    try:
        return sms_svc.send_announcement_sms(
            get_announcements_db(),
            chapter_id=user["chapter_id"],
            announcement_id=announcement_id,
            actor_id=user["id"],
            confirmed_recipient_count=body.confirmed_recipient_count,
            idempotency_key=idempotency_key,
        )
    except sms_svc.AnnouncementNotFound:
        raise HTTPException(404, "Announcement not found")
    except sms_svc.AnnouncementNotSent:
        raise HTTPException(
            422, "Announcement must be posted to the in-app feed before SMS"
        )
    except sms_svc.RecipientCountMismatch as exc:
        raise HTTPException(
            409,
            detail={
                "message": "Recipient count changed; re-confirm before sending",
                "recipient_count": exc.recipient_count,
                "no_phone_count": exc.no_phone_count,
            },
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
