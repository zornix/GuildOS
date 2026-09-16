"""The one Python enqueue path into `message_outbox`.

Lifted out of api/treasury/notifications.py, which had the only implementation,
once auth (setup/reset codes) and events (creation, role assignment) needed the
same thing. Domains keep their own `notifications.py` with the named helpers;
this is the plumbing underneath, like the rest of api/platform/.

Exactly-once: each logical event derives a deterministic `dedup_key`, the table
has a UNIQUE index on it, and an existing row short-circuits the insert — so a
retried operation enqueues nothing new.

`channel` ('email' | 'sms') decides which provider the drain uses. It defaults to
email: everything automatic is email, and SMS is reserved for the two manual
announcement blasts (ADR-0005), which are produced in plpgsql, not here.
"""

from __future__ import annotations

from api.platform.delivery import delivery_mode
from api.platform.rows import unwrap_row


def _resolve_sb(sb):
    if sb is not None:
        return sb
    from api.platform.db import get_db

    return get_db()


def enqueue(
    sb,
    *,
    event_type: str,
    chapter_id: str,
    member_id: str | None,
    target_table: str,
    target_id: str,
    dedup_key: str | None = None,
    payload: dict | None = None,
    channel: str = "email",
) -> dict | None:
    """Idempotently enqueue one notification. None when it was already queued.

    `dedup_key` defaults to "{event_type}:{target_id}" (one notification per
    logical event). Producers whose event may legitimately recur (a daily payment
    reminder, a re-issued setup code) pass their own. `payload` defaults to the
    identifying triple; extra keys ride along for the drain's message templates
    (api/cron/core/templates.py).

    Nothing is dispatched inline: the row stays 'pending' until the drain worker
    picks it up (api/cron/services/outbox_drain.py).
    """
    client = _resolve_sb(sb)
    dedup_key = dedup_key or f"{event_type}:{target_id}"
    body_payload = {
        "event_type": event_type,
        "chapter_id": chapter_id,
        "member_id": member_id,
        **(payload or {}),
    }

    existing = (
        client.table("message_outbox")
        .select("id")
        .eq("dedup_key", dedup_key)
        .maybe_single()
        .execute()
    ).data
    if existing:
        return None

    try:
        result = (
            client.table("message_outbox")
            .insert(
                {
                    "chapter_id": chapter_id,
                    "event_type": event_type,
                    "member_id": member_id,
                    "target_table": target_table,
                    "target_id": target_id,
                    "dedup_key": dedup_key,
                    "channel": channel,
                    "delivery_mode": delivery_mode(),
                    "status": "pending",
                    "payload": body_payload,
                }
            )
            .execute()
        )
    except Exception:
        # Lost a race on the UNIQUE(dedup_key) backstop → another caller enqueued
        # it first. Still exactly-once.
        return None

    return unwrap_row(result)
