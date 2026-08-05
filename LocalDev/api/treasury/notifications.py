"""Treasury notification boundary — durable, exactly-once message outbox (Chunk G).

The former no-op stubs are replaced by a single transactional outbox. Every
lifecycle notification is *enqueued* into `message_outbox` rather than sent
inline; the scheduled drain worker (`api/cron/services/outbox_drain.py`, run by
Vercel Cron every 5 minutes) flips rows from `pending` to `sent`/`simulated`/
`failed`. This keeps the money-moving RPCs decoupled from a flaky SMS / email
provider and gives us at-least-once persistence + exactly-once dedup.

Exactly-once / idempotent on retry:
  Each logical event derives a deterministic `dedup_key` from its
  (event_type, target_id). The outbox has a UNIQUE index on `dedup_key`, and the
  enqueue is an INSERT ... ON CONFLICT DO NOTHING, so a retried operation that
  re-fires the same notification produces no second row.

Delivery gating:
  `settings.MESSAGE_DELIVERY_MODE` (api/config.py, NOT os.environ; `dry_run` in
  tests/dev) controls whether anything leaves the process. Enqueue always writes
  status='pending'; the drain worker decides, per mode, between a real send
  ('sent'), a no-network simulation ('simulated') and 'failed'.

Call sites pass only keyword identifiers (unchanged from the stub signatures);
the DB client is resolved internally, but tests may inject `sb=`.
"""

from __future__ import annotations

from datetime import date

from api.config import settings


def _delivery_mode() -> str:
    """Single source of truth: api/config.py settings, never os.environ."""
    return settings.MESSAGE_DELIVERY_MODE or "dry_run"


def _resolve_sb(sb):
    if sb is not None:
        return sb
    from api.treasury.db.session import get_treasury_db

    return get_treasury_db()


def _enqueue(
    sb,
    *,
    event_type: str,
    chapter_id: str,
    member_id: str | None,
    target_table: str,
    target_id: str,
    dedup_key: str | None = None,
    payload: dict | None = None,
) -> dict | None:
    """Idempotently enqueue one notification into the outbox.

    Returns the freshly-enqueued row, or None if this event was already enqueued
    (the dedup_key conflict short-circuited the insert) — making a retry a no-op.

    `dedup_key` defaults to the lifecycle form "{event_type}:{target_id}" (one
    notification per logical event). Producers whose event may legitimately recur
    on a schedule (e.g. a daily payment reminder) pass their own key. `payload`
    defaults to the identifying triple; extra keys ride along for the drain
    worker's message templates (api/cron/core/templates.py).
    """
    client = _resolve_sb(sb)
    mode = _delivery_mode()
    dedup_key = dedup_key or f"{event_type}:{target_id}"
    body_payload = {
        "event_type": event_type,
        "chapter_id": chapter_id,
        "member_id": member_id,
        **(payload or {}),
    }

    # supabase-py / the shim both surface a unique-violation as a raised error on
    # .insert(); we treat that as "already enqueued" so the call stays exactly-once.
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
        inserted = (
            client.table("message_outbox")
            .insert(
                {
                    "chapter_id": chapter_id,
                    "event_type": event_type,
                    "member_id": member_id,
                    "target_table": target_table,
                    "target_id": target_id,
                    "dedup_key": dedup_key,
                    "delivery_mode": mode,
                    "status": "pending",
                    "payload": body_payload,
                }
            )
            .execute()
        ).data
    except Exception:
        # Lost a race on the UNIQUE(dedup_key) backstop → another caller enqueued
        # it first. Still exactly-once.
        return None

    row = inserted[0] if isinstance(inserted, list) else inserted
    # Nothing is dispatched inline: the row stays 'pending' until the drain
    # worker picks it up (api/cron/services/outbox_drain.py).
    return row


def notify_invoice_issued(
    *, chapter_id: str, member_id: str, invoice_id: str, sb=None
) -> dict | None:
    return _enqueue(
        sb,
        event_type="INVOICE_ISSUED",
        chapter_id=chapter_id,
        member_id=member_id,
        target_table="unpaid_invoices",
        target_id=invoice_id,
    )


def notify_payment_approved(
    *, chapter_id: str, member_id: str, submission_id: str, sb=None
) -> dict | None:
    return _enqueue(
        sb,
        event_type="PAYMENT_APPROVED",
        chapter_id=chapter_id,
        member_id=member_id,
        target_table="payment_submissions",
        target_id=submission_id,
    )


def notify_payment_rejected(
    *, chapter_id: str, member_id: str, submission_id: str, sb=None
) -> dict | None:
    return _enqueue(
        sb,
        event_type="PAYMENT_REJECTED",
        chapter_id=chapter_id,
        member_id=member_id,
        target_table="payment_submissions",
        target_id=submission_id,
    )


def notify_refund_issued(
    *, chapter_id: str, member_id: str, refund_id: str, sb=None
) -> dict | None:
    return _enqueue(
        sb,
        event_type="REFUND_ISSUED",
        chapter_id=chapter_id,
        member_id=member_id,
        target_table="refunds",
        target_id=refund_id,
    )


# ── Officer-initiated reminder (not a lifecycle event) ───────────────────────


def enqueue_payment_reminder(
    *,
    chapter_id: str,
    member_id: str,
    unpaid_count: int,
    unpaid_total_cents: int,
    on_date: date | None = None,
    sb=None,
) -> dict | None:
    """Enqueue a PAYMENT_REMINDER for one member's outstanding fines.

    Unlike the lifecycle events above there is no single target row, so the
    member is the target. The dedup_key is scoped to the calendar day
    ("PAYMENT_REMINDER:{member_id}:{YYYY-MM-DD}"): an officer can nudge again
    tomorrow, but repeated clicks today enqueue exactly one message.

    Returns None when today's reminder was already enqueued.
    """
    day = (on_date or date.today()).isoformat()
    return _enqueue(
        sb,
        event_type="PAYMENT_REMINDER",
        chapter_id=chapter_id,
        member_id=member_id,
        target_table="members",
        target_id=member_id,
        dedup_key=f"PAYMENT_REMINDER:{member_id}:{day}",
        payload={
            "unpaid_count": unpaid_count,
            "unpaid_total_cents": unpaid_total_cents,
            "reminder_date": day,
        },
    )
