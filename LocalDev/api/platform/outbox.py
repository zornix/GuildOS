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
    (api/cron/core/templates.py).

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
        result = client.table("message_outbox").insert(row).execute()
    except Exception:
        # Lost a race on the UNIQUE(dedup_key) backstop → another caller enqueued
        # it first. Still exactly-once.
        return None

    return unwrap_row(result)


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
    """Fan one notification out to many members in two queries, not 2N.

    `dedup_key_for(member_id) -> str`. Same exactly-once guarantee as `enqueue`:
    already-queued keys are dropped up front, and if the bulk insert loses a race
    on UNIQUE(dedup_key) each remaining row falls back to `enqueue`. Returns the
    number of rows queued.
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
    queued = (
        client.table("message_outbox")
        .select("dedup_key")
        .in_("dedup_key", sorted(rows))
        .execute()
    ).data or []
    for existing in queued:
        rows.pop(existing["dedup_key"], None)
    if not rows:
        return 0

    try:
        client.table("message_outbox").insert(list(rows.values())).execute()
        return len(rows)
    except Exception:
        pass

    return sum(
        1
        for row in rows.values()
        if enqueue(
            client,
            event_type=event_type,
            chapter_id=chapter_id,
            member_id=row["member_id"],
            target_table=target_table,
            target_id=target_id,
            dedup_key=row["dedup_key"],
            payload=payload,
            channel=channel,
        )
    )
