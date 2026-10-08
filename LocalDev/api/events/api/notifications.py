"""Events notify-gate HTTP surface. Mounted at `/api/events` by router.py.

Two routes: a preview (checklist + recipient counts, no side effects) and the
confirmed send. Business logic lives in
`api/events/services/notifications.py`; handlers are thin (parse -> service
-> respond).
"""

from __future__ import annotations

from contextlib import contextmanager

from fastapi import APIRouter, Depends, Header, HTTPException

from api.announcements.services.sms import RecipientCountMismatch
from api.dependencies import get_current_user
from api.platform.db import get_db
from api.events.services import events as events_svc
from api.events.services import notifications as svc

from .schemas import NotifyConfirm

router = APIRouter()


@contextmanager
def _map_domain_errors():
    try:
        yield
    except events_svc.EventNotFound as exc:
        raise HTTPException(404, str(exc) or "Event not found")
    except events_svc.NotPermitted as exc:
        raise HTTPException(403, str(exc))
    except svc.EventIncomplete as exc:
        raise HTTPException(
            409,
            detail={
                "message": "Event is not complete enough to notify",
                "completeness": exc.completeness,
            },
        )
    except RecipientCountMismatch as exc:
        raise HTTPException(
            409,
            detail={
                "message": "Recipient count changed; re-confirm before sending",
                "recipient_count": exc.recipient_count,
                "no_phone_count": exc.no_phone_count,
            },
        )
    except svc.NotifyCooldown as exc:
        raise HTTPException(429, str(exc))
    except svc.NoRecipients as exc:
        raise HTTPException(409, str(exc))


@router.get("/{event_id}/notify-preview")
def notify_preview(event_id: str, user=Depends(get_current_user)):
    """Confirmation step: checklist + who this would reach. No side effects."""
    with _map_domain_errors():
        return svc.preview_notify(get_db(), actor=user, event_id=event_id)


@router.post("/{event_id}/notify")
def notify(
    event_id: str,
    body: NotifyConfirm,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Two-phase confirmed notify blast. 409 returns fresh counts to re-confirm."""
    with _map_domain_errors():
        return svc.notify_event(
            get_db(),
            actor=user,
            event_id=event_id,
            confirmed_recipient_count=body.confirmed_recipient_count,
            idempotency_key=idempotency_key,
        )
