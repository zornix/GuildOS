"""Events notify gate — completeness-gated "Notify members" SMS blast.

Spec §2.1/§2.7/§5, docs/imp-ev-ph2.md. Sends to all chapter members (spec:
"Notify: ... Sends to all members"); reuses the announcements SMS dispatch
path (api/announcements/services/sms.py) — `resolve_recipients` for audience
resolution and `dispatch_send` (send_table="event_notification_sends") for
delivery — rather than a second Twilio integration.

Storage/RPC: `ev_notify_event` (migration 0143). Authorization (decision D5):
a supervisor or organizer of the event, or a holder of calendar:event:update.
The completeness gate (>=1 supervisor, >=1 organizer, >=3 jobs) and the
1/hour cooldown are enforced in the RPC as the trust boundary; this module
pre-checks completeness so the HTTP layer can return a precise 409 without a
round trip, and maps the RPC's own guard failures (defense in depth) too.

No FastAPI imports here — routes translate the domain exceptions below into
HTTP status codes.
"""

from __future__ import annotations

from api.announcements.services.sms import (
    RecipientCountMismatch,
    dispatch_send,
    resolve_recipients,
)
from api.events.auth import EVENT_UPDATE
from api.events.core.rules import completeness as compute_completeness
from api.platform.rpc import call_rpc
from api.events.services.events import (
    EventsError,
    EventNotFound,  # noqa: F401  (re-exported for route error mapping)
    NotPermitted,
    _actor_is_supervisor,
    _get_event_row,
    _job_counts_for_event,
    _last_notified_at,
    _organizers_for_event,
    _supervisors_for_event,
)
from api.rbac.services.permissions import has_permission
from api.platform.delivery import delivery_mode

SEND_TABLE = "event_notification_sends"


class EventIncomplete(EventsError):
    """The notify-gate completeness check failed (HTTP 409)."""

    def __init__(self, completeness: dict):
        self.completeness = completeness
        super().__init__("Event is not complete enough to notify")


class NotifyCooldown(EventsError):
    """A notify blast for this event was already sent within the last hour
    (HTTP 429)."""


class NoRecipients(EventsError):
    """No SMS-reachable recipients were resolved (HTTP 409)."""


def _actor_is_organizer(sb, *, event_id: str, member_id: str) -> bool:
    return bool(
        (
            sb.table("event_organizers")
            .select("id")
            .eq("event_id", event_id)
            .eq("member_id", member_id)
            .execute()
        ).data
    )


def _require_notify(sb, *, actor: dict, event_id: str) -> None:
    """D5: supervisor OR organizer OR calendar:event:update."""
    if _actor_is_supervisor(sb, event_id=event_id, member_id=actor["id"]):
        return
    if _actor_is_organizer(sb, event_id=event_id, member_id=actor["id"]):
        return
    if has_permission(actor, EVENT_UPDATE, sb=sb):
        return
    raise NotPermitted(
        "Notifying this event requires being a supervisor/organizer of it "
        "or holding calendar:event:update"
    )


def _completeness_for_event(sb, *, event_id: str) -> tuple[dict, int]:
    """(completeness_dict, open_job_count) for the notify gate + message body."""
    supervisor_count = len(_supervisors_for_event(sb, event_id))
    organizer_count = len(_organizers_for_event(sb, event_id))
    job_count, open_job_count = _job_counts_for_event(sb, event_id)
    gate = compute_completeness(
        supervisor_count=supervisor_count,
        organizer_count=organizer_count,
        job_count=job_count,
    )
    return gate, open_job_count


def _notify_body(event: dict, open_job_count: int) -> str:
    """"{title} — {date} {time}. {n} open jobs." (spec §2 Notify section)."""
    return f"{event['title']} — {event['date']} {event['time']}. {open_job_count} open jobs."


def preview_notify(sb, *, actor: dict, event_id: str) -> dict:
    """The confirmation-step payload: gate status + who this would reach."""
    chapter_id = actor["chapter_id"]
    event = _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)
    _require_notify(sb, actor=actor, event_id=event_id)

    gate, open_job_count = _completeness_for_event(sb, event_id=event_id)
    resolved = resolve_recipients(sb, chapter_id=chapter_id, audience="chapter")

    return {
        "event_id": event_id,
        "completeness": gate,
        "recipient_count": resolved["recipient_count"],
        "no_phone_count": resolved["no_phone_count"],
        "no_consent_count": resolved["no_consent_count"],
        "body_preview": _notify_body(event, open_job_count),
        "last_notified_at": _last_notified_at(sb, event_id),
    }


def notify_event(
    sb,
    *,
    actor: dict,
    event_id: str,
    confirmed_recipient_count: int,
    idempotency_key: str | None = None,
) -> dict:
    chapter_id = actor["chapter_id"]
    event = _get_event_row(sb, chapter_id=chapter_id, event_id=event_id)
    _require_notify(sb, actor=actor, event_id=event_id)

    gate, open_job_count = _completeness_for_event(sb, event_id=event_id)
    if not gate["is_complete"]:
        raise EventIncomplete(gate)

    resolved = resolve_recipients(sb, chapter_id=chapter_id, audience="chapter")
    if not resolved["recipient_member_ids"]:
        raise NoRecipients("No SMS-reachable members to notify")
    if confirmed_recipient_count != resolved["recipient_count"]:
        raise RecipientCountMismatch(
            resolved["recipient_count"], resolved["no_phone_count"]
        )

    body = _notify_body(event, open_job_count)

    try:
        send_row = call_rpc(
            "ev_notify_event",
            {
                "p_chapter_id": chapter_id,
                "p_event_id": event_id,
                "p_actor_id": actor["id"],
                "p_recipient_member_ids": resolved["recipient_member_ids"],
                "p_body_snapshot": body,
                "p_delivery_mode": delivery_mode(),
                "p_idempotency_key": idempotency_key,
            },
            sb=sb,
        ).data
    except Exception as exc:  # RPC-side guard failures (defense in depth)
        msg = str(exc)
        if "event_incomplete" in msg:
            raise EventIncomplete(gate) from exc
        if "notify_cooldown" in msg:
            raise NotifyCooldown("Event was already notified within the last hour") from exc
        if "no_recipients" in msg:
            raise NoRecipients("No recipients to notify") from exc
        raise

    return dispatch_send(sb, send_row, send_table=SEND_TABLE)
