"""Announcements HTTP surface. Mounted under `/api/announcements` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from api.announcements.api.schemas import AnnouncementCreate, SmsSendConfirm
from api.announcements.auth import (
    ANNOUNCEMENTS_CREATE,
    ANNOUNCEMENTS_SEND,
    ANNOUNCEMENTS_SEND_SMS,
)
from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.announcements.services import announcements as svc
from api.announcements.services import outbox as outbox_svc
from api.announcements.services import sms as sms_svc
from api.dependencies import get_current_user
from api.rbac.services.permissions import has_permission

router = APIRouter()

# Reading treasury messages in the outbox is treasury row access, same key the
# treasury surfaces use (api/treasury/api/balances.py).
TREASURY_AUDIT_VIEW = "treasury:audit:view"


@router.get("/")
async def list_announcements(status: str | None = None, user=Depends(get_current_user)):
    """List chapter announcements. Any authenticated member can view.

    Not a 403 surface: members simply get the filtered feed — sent
    announcements whose audience includes them. Drafts (and the `status`
    filter) belong to announcements:create holders.
    """
    sb = get_db()
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
        get_db(),
        chapter_id=user["chapter_id"],
        title=body.title,
        body=body.body,
        audience=body.audience,
        actor_id=user["id"],
        calendar_date=body.calendar_date.isoformat() if body.calendar_date else None,
        calendar_time=body.calendar_time.isoformat() if body.calendar_time else None,
    )


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    user=Depends(require_permission(ANNOUNCEMENTS_CREATE)),
):
    """Drop a draft, or retire a sent announcement from the calendar (D15).

    DELETE-only, so it cannot shadow GET /sms-log; the /{id}/sms-preview |
    send-sms | send paths are longer and cannot collide with it either.
    """
    try:
        return svc.hide_from_calendar(
            get_db(),
            chapter_id=user["chapter_id"],
            announcement_id=announcement_id,
        )
    except svc.AnnouncementNotFound:
        raise HTTPException(404, "Announcement not found")


@router.get("/sms-log")
async def sms_log(
    limit: int = 50,
    user=Depends(require_permission(ANNOUNCEMENTS_SEND)),
):
    """Every SMS send with sender attribution, newest first (exec visibility)."""
    return sms_svc.list_sms_log(
        get_db(), chapter_id=user["chapter_id"], limit=limit
    )


@router.get("/outbox")
async def list_outbox(
    status: str | None = None,
    limit: int = outbox_svc.LIST_LIMIT_DEFAULT,
    user=Depends(require_permission(ANNOUNCEMENTS_SEND)),
):
    """The chapter's message_outbox, newest first (issue #48)."""
    return outbox_svc.list_outbox(
        get_db(),
        chapter_id=user["chapter_id"],
        status=status,
        limit=limit,
        include_treasury=has_permission(user, TREASURY_AUDIT_VIEW),
    )


@router.post("/outbox/{row_id}/retry")
async def retry_outbox(
    row_id: str,
    user=Depends(require_permission(ANNOUNCEMENTS_SEND)),
):
    """Requeue a failed row; the next cron drain picks it up."""
    try:
        return outbox_svc.retry_outbox_row(
            get_db(),
            chapter_id=user["chapter_id"],
            row_id=row_id,
            actor_id=user["id"],
            include_treasury=has_permission(user, TREASURY_AUDIT_VIEW),
        )
    except outbox_svc.OutboxRowNotRetryable:
        raise HTTPException(409, "This message carried a one-time code. Send the member a new code instead.")
    except outbox_svc.OutboxRowNotFound:
        raise HTTPException(404, "Outbox message not found")
    except outbox_svc.OutboxRowNotFailed as exc:
        raise HTTPException(409, f"Only failed messages can be retried (status: {exc.status})")


@router.get("/{announcement_id}/sms-preview")
async def sms_preview(
    announcement_id: str,
    user=Depends(require_permission(ANNOUNCEMENTS_SEND_SMS)),
):
    """Confirmation step: who would the blast reach right now?"""
    try:
        return sms_svc.preview_sms(
            get_db(),
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
            get_db(),
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
        get_db(),
        chapter_id=user["chapter_id"],
        announcement_id=announcement_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )
