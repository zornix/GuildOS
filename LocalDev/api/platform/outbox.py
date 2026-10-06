"""The one Python enqueue path into `message_outbox`.

Lifted out of api/treasury/notifications.py, which had the only implementation,
once auth (setup/reset codes) and events (creation, role assignment) needed the
same thing. Domains keep their own `notifications.py` with the named helpers;
this is the plumbing underneath, like the rest of api/platform/.

Exactly-once: each logical event derives a deterministic `dedup_key`, the table
has a UNIQUE index on it, and the insert is ON CONFLICT (dedup_key) DO NOTHING —
so a retried operation enqueues nothing new. Any other insert failure is a real
failure: logged and swallowed for a plain client (the caller's work already
committed), raised for a transaction client (so the transaction rolls back).

`channel` ('email' | 'sms') decides which provider the drain uses. It defaults to
email: everything automatic is email, and SMS is reserved for the two manual
announcement blasts (ADR-0005), which are produced in plpgsql, not here.
"""

from __future__ import annotations

import logging

from api.platform.delivery import delivery_mode

logger = logging.getLogger(__name__)


def _resolve_sb(sb):
    if sb is not None:
        return sb
    from api.platform.db import get_db

    return get_db()


def _insert_ignoring_duplicates(client, rows, what: str):
    """INSERT … ON CONFLICT (dedup_key) DO NOTHING. Returns the inserted rows, or
    None after logging when a plain client hits a real error. Inside a
    transaction the error propagates."""
    try:
        return client.table("message_outbox").insert(rows, ignore_conflict="dedup_key").execute().data or []
    except Exception as exc:
        if getattr(getattr(client, "_pool", None), "in_tx", False):
            raise
        # Primary message only, no traceback: the DETAIL line quotes the failing
        # row, and auth payloads carry live one-time codes.
        reason = getattr(getattr(exc, "diag", None), "message_primary", None) or type(exc).__name__
        logger.error("outbox enqueue failed for %s: %s", what, reason)
        return None


def _row(
    *, event_type, chapter_id, member_id, target_table, target_id, dedup_key,
    payload, channel,
) -> dict:
    return {
        "chapter_id": chapter_id,
        "event_type": event_type,
        "member_id": member_id,
        "target_table": target_table,
        "target_id": target_id,
        "dedup_key": dedup_key,
        "channel": channel,
        "delivery_mode": delivery_mode(),
        "status": "pending",
        "payload": {
            "event_type": event_type,
            "chapter_id": chapter_id,
            "member_id": member_id,
            **(payload or {}),
        },
    }


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
    (api/platform/message_templates.py).

    Nothing is dispatched inline: the row stays 'pending' until the drain worker
    picks it up (api/cron/services/outbox_drain.py).
    """
    client = _resolve_sb(sb)
    dedup_key = dedup_key or f"{event_type}:{target_id}"
    row = _row(
        event_type=event_type,
        chapter_id=chapter_id,
        member_id=member_id,
        target_table=target_table,
        target_id=target_id,
        dedup_key=dedup_key,
        payload=payload,
        channel=channel,
    )

    inserted = _insert_ignoring_duplicates(client, row, dedup_key)
    return inserted[0] if inserted else None


def enqueue_many(
    sb,
    *,
    event_type: str,
    chapter_id: str,
    target_table: str,
    target_id: str,
    member_ids: list[str],
    dedup_key_for,
    payload: dict | None = None,
    channel: str = "email",
) -> int:
    """Fan one notification out to many members in one query, not N.

    `dedup_key_for(member_id) -> str`. Same exactly-once guarantee and error rule
    as `enqueue`: one bulk insert, already-queued keys are skipped by the
    database. Returns the number of rows queued.
    """
    if not member_ids:
        return 0
    client = _resolve_sb(sb)

    rows = {
        dedup_key_for(member_id): _row(
            event_type=event_type,
            chapter_id=chapter_id,
            member_id=member_id,
            target_table=target_table,
            target_id=target_id,
            dedup_key=dedup_key_for(member_id),
            payload=payload,
            channel=channel,
        )
        for member_id in member_ids
    }
    inserted = _insert_ignoring_duplicates(client, list(rows.values()), f"{event_type}:{target_id}")
    return len(inserted or [])
