"""Treasury notification boundary — durable, exactly-once message outbox (Chunk G).

Every lifecycle notification is *enqueued* into `message_outbox` rather than
sent inline; the scheduled drain worker (`api/cron/services/outbox_drain.py`,
run by Vercel Cron every 5 minutes) flips rows from `pending` to `sent`/
`simulated`/`failed`. This keeps the money-moving RPCs decoupled from a flaky
SMS / email provider. The enqueue itself lives in api/platform/outbox.py — auth
and events use the same one. Every treasury notification is email (ADR-0005).

Not transactional with the money:
  The enqueue runs after the money RPC has committed, in a separate statement.
  If it fails, the invoice/payment/refund stays committed and the notification
  is missing; the failure is logged (logger `api.platform.outbox`), not raised,
  unless the caller passed a transaction client as `sb`, in which case it
  propagates and rolls that transaction back.

Exactly-once / idempotent on retry:
  Each logical event derives a deterministic `dedup_key` from its
  (event_type, target_id). The outbox has a UNIQUE index on `dedup_key`, and the
  enqueue is an INSERT ... ON CONFLICT (dedup_key) DO NOTHING, so a retried
  operation that re-fires the same notification produces no second row.

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

from api.platform.outbox import enqueue as _enqueue


def notify_invoice_issued(
    *, chapter_id: str, member_id: str, invoice_id: str, sb=None
) -> dict | None:
    return _enqueue(
        sb,
        channel="email",
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
        channel="email",
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
        channel="email",
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
        channel="email",
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
        channel="email",
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
