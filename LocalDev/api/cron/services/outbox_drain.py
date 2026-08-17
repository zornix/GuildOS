"""The message_outbox drain worker — GTMLarpChecklist 2.1.

Before this existed, the only dispatcher was `dispatch_send`
(api/announcements/services/sms.py), called inline in an HTTP request and scoped
to a single send-log row by target_table/target_id. Every other outbox row —
every treasury lifecycle notification, every job report/approval/rejection, every
security assignment and swap — sat 'pending' forever. A member was never told
their payment was approved or that they caught a security shift.

This module sweeps the whole table: oldest pending rows first, one batch per run,
invoked by Vercel Cron every 5 minutes (GET /api/cron/drain-outbox, authenticated
by CRON_SECRET). It is deliberately cross-chapter — it is a system worker, not a
tenant-scoped request path, and it runs on the admin client.

Per row it is total: every row it touches leaves 'pending' for a terminal status
('sent', 'simulated' or 'failed' with `last_error`), and no single bad row can
abort the batch. Because terminal rows are never re-selected there is no retry
storm and no infinite redelivery; a 'failed' row is a signal for an operator, not
something the worker keeps hammering. `attempts` still increments so a future
retry policy has the number it needs.

Single-row UPDATEs go through the table client rather than a plpgsql RPC: this is
delivery bookkeeping on a non-financial table, not a trust-boundary mutation, and
it matches how every other outbox write in the codebase is done.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from api.announcements.services import twilio_client
from api.config import settings
from api.cron.core import templates

logger = logging.getLogger(__name__)

DEFAULT_BATCH_LIMIT = 100

# The two real dispatch modes. `message_outbox.delivery_mode` also holds channel
# labels written by the RPCs ('sms'), which are not dispatch modes — a row value
# only overrides the global setting when it names one of these.
DRY_RUN = "dry_run"
TWILIO = "twilio"
_DISPATCH_MODES = (DRY_RUN, TWILIO)

# event_type -> (target table, columns) used to enrich a payload with facts the
# producer did not inline. The treasury enqueue path writes identifiers only, so
# the amount a member is being told about has to be read from the target row.
_ENRICHMENT: dict[str, tuple[str, str]] = {
    "INVOICE_ISSUED": ("unpaid_invoices", "amount_cents, kind, description"),
    "PAYMENT_APPROVED": ("payment_submissions", "claimed_amount_cents"),
    "PAYMENT_REJECTED": ("payment_submissions", "claimed_amount_cents"),
    "REFUND_ISSUED": ("refunds", "amount_cents, reason"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_sb(sb):
    if sb is not None:
        return sb
    from api.platform.db import get_db

    return get_db()


def _global_mode() -> str:
    mode = settings.MESSAGE_DELIVERY_MODE or DRY_RUN
    if mode not in _DISPATCH_MODES:
        # Fail the whole run loudly: a typo in the Vercel env var must not
        # silently simulate (or silently skip) every message (checklist 2.2).
        raise ValueError(
            f"Unknown MESSAGE_DELIVERY_MODE {mode!r}; expected 'dry_run' or 'twilio'"
        )
    return mode


def _row_mode(row: dict, default: str) -> str:
    candidate = (row.get("delivery_mode") or "").strip()
    return candidate if candidate in _DISPATCH_MODES else default


def _enrich(sb, row: dict) -> dict:
    """Payload + the target row's facts. A lookup miss is never fatal."""
    payload = dict(row.get("payload") or {})
    spec = _ENRICHMENT.get(row["event_type"])
    if not spec:
        return payload
    table, columns = spec
    try:
        target = (
            sb.table(table)
            .select(columns)
            .eq("id", row["target_id"])
            .maybe_single()
            .execute()
        ).data
    except Exception:
        logger.warning(
            "outbox %s: could not read %s/%s for enrichment",
            row.get("id"),
            table,
            row.get("target_id"),
            exc_info=True,
        )
        return payload
    if target:
        # Producer-supplied payload keys win over the looked-up ones.
        payload = {**target, **payload}
    return payload


def _member_phone(sb, member_id: str) -> str:
    member = (
        sb.table("members")
        .select("id, phone")
        .eq("id", member_id)
        .maybe_single()
        .execute()
    ).data
    return ((member or {}).get("phone") or "").strip()


def _close_row(sb, row: dict, *, status: str, last_error: str | None) -> None:
    patch = {
        "status": status,
        "attempts": (row.get("attempts") or 0) + 1,
        "last_error": last_error[:1000] if last_error else None,
    }
    if status == "sent":
        patch["delivered_at"] = _now_iso()
    sb.table("message_outbox").update(patch).eq("id", row["id"]).execute()


def _deliver_row(sb, row: dict, *, default_mode: str) -> str:
    """Deliver one row. Returns its terminal status; never raises."""
    try:
        if not row.get("member_id"):
            # Chapter-wide events (ANNOUNCEMENT_PUBLISHED) have no SMS recipient;
            # they exist for the in-app feed. Close them out honestly instead of
            # leaving them pending forever.
            _close_row(sb, row, status="failed", last_error="no member_id (no recipient)")
            return "failed"

        payload = _enrich(sb, row)
        body = templates.render(row["event_type"], payload)
        mode = _row_mode(row, default_mode)

        if mode == DRY_RUN:
            _close_row(sb, row, status="simulated", last_error=None)
            return "simulated"

        phone = _member_phone(sb, row["member_id"])
        if not phone:
            _close_row(sb, row, status="failed", last_error="no phone")
            return "failed"

        twilio_client.send_sms(phone, body)
        _close_row(sb, row, status="sent", last_error=None)
        return "sent"
    except Exception as exc:
        logger.exception("outbox drain failed for row %s", row.get("id"))
        detail = f"{type(exc).__name__}: {exc}"
        try:
            _close_row(sb, row, status="failed", last_error=detail)
        except Exception:
            # Even the bookkeeping write failed (row vanished, DB blip). Leave it
            # pending for the next run rather than killing the batch.
            logger.exception("could not record failure for outbox row %s", row.get("id"))
        return "failed"


def drain_outbox(
    sb=None, *, limit: int = DEFAULT_BATCH_LIMIT, chapter_id: str | None = None
) -> dict:
    """Deliver up to `limit` pending outbox rows, oldest first.

    `chapter_id` narrows the sweep to one tenant — used by tests and by an
    operator draining a single chapter by hand. The scheduled run passes nothing
    and sweeps every chapter.

    Returns {"processed", "sent", "simulated", "failed"}.
    """
    client = _resolve_sb(sb)
    default_mode = _global_mode()

    query = client.table("message_outbox").select("*").eq("status", "pending")
    if chapter_id:
        query = query.eq("chapter_id", chapter_id)
    pending = (query.order("created_at").limit(limit).execute()).data or []

    counts = {"processed": 0, "sent": 0, "simulated": 0, "failed": 0}
    for row in pending:
        status = _deliver_row(client, row, default_mode=default_mode)
        counts["processed"] += 1
        counts[status] = counts.get(status, 0) + 1

    if counts["processed"]:
        logger.info("outbox drain: %s", counts)
    return counts
