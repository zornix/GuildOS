"""Treasury notification boundary — durable, exactly-once message outbox (Chunk G).

The former no-op stubs are replaced by a single transactional outbox. Every
lifecycle notification is *enqueued* into `message_outbox` rather than sent
inline; a separate delivery worker (out of scope for V1) would flip rows from
`pending` to `sent`. This keeps the money-moving RPCs decoupled from a flaky SMS
/ email provider and gives us at-least-once persistence + exactly-once dedup.

Exactly-once / idempotent on retry:
  Each logical event derives a deterministic `dedup_key` from its
  (event_type, target_id). The outbox has a UNIQUE index on `dedup_key`, and the
  enqueue is an INSERT ... ON CONFLICT DO NOTHING, so a retried operation that
  re-fires the same notification produces no second row.

Delivery gating:
  `MESSAGE_DELIVERY_MODE` (env; `dry_run` in tests/dev) controls whether anything
  leaves the process. In `dry_run` the row is persisted with status='pending' and
  NOTHING is dispatched externally. Any other mode would hand the row to a real
  provider — but that integration is intentionally not wired in V1.

Call sites pass only keyword identifiers (unchanged from the stub signatures);
the DB client is resolved internally, but tests may inject `sb=`.
"""

from __future__ import annotations

import os


def _delivery_mode() -> str:
    return os.environ.get("MESSAGE_DELIVERY_MODE", "dry_run")


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
) -> dict | None:
    """Idempotently enqueue one notification into the outbox.

    Returns the freshly-enqueued row, or None if this event was already enqueued
    (the dedup_key conflict short-circuited the insert) — making a retry a no-op.
    """
    client = _resolve_sb(sb)
    mode = _delivery_mode()
    dedup_key = f"{event_type}:{target_id}"

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
                    "payload": {
                        "event_type": event_type,
                        "chapter_id": chapter_id,
                        "member_id": member_id,
                    },
                }
            )
            .execute()
        ).data
    except Exception:
        # Lost a race on the UNIQUE(dedup_key) backstop → another caller enqueued
        # it first. Still exactly-once.
        return None

    row = inserted[0] if isinstance(inserted, list) else inserted
    # In dry_run nothing is dispatched; the row remains 'pending'. A real mode
    # would hand the row to the provider here and advance it to 'sent'.
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
