"""The message_outbox drain worker — GTMLarpChecklist 2.1.

Before this existed, the only dispatcher was `dispatch_send`
(api/announcements/services/sms.py), called inline in an HTTP request and scoped
to a single send-log row by target_table/target_id. Every other outbox row —
every treasury lifecycle notification, every job report/approval/rejection, every
security assignment and swap — sat 'pending' forever. A member was never told
their payment was approved or that they caught a security shift.

Two channels (0159 / ADR-0005): a row's `channel` decides its provider — 'sms'
goes to Twilio with the consent check, 'email' to api/platform/email.py without
one. MESSAGE_DELIVERY_MODE governs SMS, EMAIL_DELIVERY_MODE email; either in
dry_run marks its rows 'simulated'.

This module sweeps the whole table: oldest pending rows first, one batch per run,
invoked by Vercel Cron every 5 minutes (GET /api/cron/drain-outbox, authenticated
by CRON_SECRET). It is deliberately cross-chapter — it is a system worker, not a
tenant-scoped request path, and it runs on the admin client.

A batch is *claimed* before anything is delivered: `outbox_claim_batch`
(migrations/0155) flips its rows to 'sending' in the same statement that selects
them, under FOR UPDATE SKIP LOCKED, so two overlapping runs — the 5-minute cron
overtaking a slow batch, or an operator draining one chapter by hand — cannot
both hold the same row and send the same member two messages (issue #32). The
claim also requeues rows whose worker died with them (claimed over 15 minutes
ago) and fails rows past 5 attempts, so nothing is stranded and nothing is
retried forever.

Per row it is total: every claimed row leaves 'sending' for a terminal status
('sent', 'simulated' or 'failed' with `last_error`), and no single bad row can
abort the batch. Terminal rows are never claimed again, so a 'failed' row is a
signal for an operator, not something the worker keeps hammering.

Single-row UPDATEs go through the table client rather than a plpgsql RPC: this is
delivery bookkeeping on a non-financial table, not a trust-boundary mutation, and
it matches how every other outbox write in the codebase is done. The claim is the
exception, and has to be: it is one atomic select-and-mark.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from api.announcements.services import twilio_client
from api.cron.core import templates
from api.platform.delivery import delivery_mode
from api.platform.email import email_delivery_mode, send_email
from api.platform.rpc import call_rpc
from api.sms_consent import CONSENT_COLUMNS, has_consent

logger = logging.getLogger(__name__)

DEFAULT_BATCH_LIMIT = 100

# The two real dispatch modes. `message_outbox.delivery_mode` is NOT one of these
# knobs: it is a snapshot of the mode at enqueue time (0070 defaults it to
# 'dry_run' and the plpgsql producers never set it), so the live setting decides
# how a row is delivered — see _global_mode.
DRY_RUN = "dry_run"
TWILIO = "twilio"
SMTP = "smtp"
_DISPATCH_MODES = (DRY_RUN, TWILIO)
_EMAIL_MODES = (DRY_RUN, SMTP)

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


def _email_mode() -> str:
    """The email twin of _global_mode: dry_run simulates, smtp really sends."""
    mode = email_delivery_mode()
    if mode not in _EMAIL_MODES:
        raise ValueError(
            f"Unknown EMAIL_DELIVERY_MODE {mode!r}; expected 'dry_run' or 'smtp'"
        )
    return mode


def _global_mode() -> str:
    """The mode every row is delivered in: the live setting, not the row's.

    `message_outbox.delivery_mode` records what the mode was when the row was
    enqueued; treating it as an override pinned every row queued before the
    twilio flip — and every plpgsql-produced row, which takes 0070's 'dry_run'
    column default — to a simulated delivery forever.
    """
    mode = delivery_mode()
    if mode not in _DISPATCH_MODES:
        # Fail the whole run loudly: a typo in the Vercel env var must not
        # silently simulate (or silently skip) every message (checklist 2.2).
        raise ValueError(
            f"Unknown MESSAGE_DELIVERY_MODE {mode!r}; expected 'dry_run' or 'twilio'"
        )
    return mode


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


def _member_sms(sb, member_id: str) -> dict:
    """The member row the delivery decision needs: phone plus consent state."""
    return (
        sb.table("members")
        .select(f"id, phone, {CONSENT_COLUMNS}")
        .eq("id", member_id)
        .maybe_single()
        .execute()
    ).data or {}


def _member_email(sb, member_id: str) -> str:
    row = (
        sb.table("members").select("id, email").eq("id", member_id).maybe_single().execute()
    ).data or {}
    return (row.get("email") or "").strip()


def _close_row(sb, row: dict, *, status: str, last_error: str | None) -> None:
    """Move a claimed row from 'sending' to its terminal status.

    `attempts` is not touched here: outbox_claim_batch increments it when it
    hands the row over, so an attempt that kills the worker outright still
    counts against the cap.
    """
    patch = {
        "status": status,
        "last_error": last_error[:1000] if last_error else None,
    }
    if status == "sent":
        patch["delivered_at"] = _now_iso()
    sb.table("message_outbox").update(patch).eq("id", row["id"]).execute()


def _chapter_name(sb, chapter_id, cache: dict) -> str:
    """Chapter name for the message footer, looked up once per batch."""
    key = str(chapter_id)
    if key not in cache:
        row = (
            sb.table("chapters")
            .select("name")
            .eq("id", chapter_id)
            .maybe_single()
            .execute()
        ).data
        cache[key] = (row or {}).get("name") or ""
    return cache[key]


def _deliver_sms(sb, row: dict, *, mode: str, chapter_name: str, payload: dict) -> str:
    body = templates.render(
        row["event_type"], payload, chapter_name=chapter_name, channel="sms"
    )
    if mode == DRY_RUN:
        _close_row(sb, row, status="simulated", last_error=None)
        return "simulated"

    member = _member_sms(sb, row["member_id"])
    phone = (member.get("phone") or "").strip()
    if not phone:
        _close_row(sb, row, status="failed", last_error="no phone")
        return "failed"
    if not has_consent(member):
        # Texting without prior express consent is the carrier violation that
        # gets a sender shut off (#57). A real send is refused; dry_run above
        # still simulates it, so local dev keeps showing the message.
        _close_row(sb, row, status="failed", last_error="no_consent")
        return "failed"

    twilio_client.send_sms(phone, body)
    _close_row(sb, row, status="sent", last_error=None)
    return "sent"


def _deliver_email(sb, row: dict, *, chapter_name: str, payload: dict) -> str:
    """Email needs no consent check: this is transactional mail to a member of
    the chapter that is writing to them (ADR-0005)."""
    subject, body = templates.render_email(
        row["event_type"], payload, chapter_name=chapter_name
    )
    if _email_mode() == DRY_RUN:
        _close_row(sb, row, status="simulated", last_error=None)
        return "simulated"

    address = _member_email(sb, row["member_id"])
    if not address:
        _close_row(sb, row, status="failed", last_error="no_email")
        return "failed"

    send_email(address, subject, body)
    _close_row(sb, row, status="sent", last_error=None)
    return "sent"


def _deliver_row(sb, row: dict, *, mode: str, names: dict) -> str:
    """Deliver one row by its channel. Returns its terminal status; never raises.

    `mode` is the SMS mode; the email mode is read per row from settings.
    """
    try:
        if not row.get("member_id"):
            # Chapter-wide events (ANNOUNCEMENT_PUBLISHED) have no recipient;
            # they exist for the in-app feed. Close them out honestly instead of
            # leaving them pending forever.
            _close_row(sb, row, status="failed", last_error="no member_id (no recipient)")
            return "failed"

        payload = _enrich(sb, row)
        chapter_name = _chapter_name(sb, row["chapter_id"], names)
        if (row.get("channel") or "email") == "sms":
            return _deliver_sms(
                sb, row, mode=mode, chapter_name=chapter_name, payload=payload
            )
        return _deliver_email(sb, row, chapter_name=chapter_name, payload=payload)
    except Exception as exc:
        logger.exception("outbox drain failed for row %s", row.get("id"))
        detail = f"{type(exc).__name__}: {exc}"
        try:
            _close_row(sb, row, status="failed", last_error=detail)
        except Exception:
            # Even the bookkeeping write failed (row vanished, DB blip). The row
            # stays 'sending' and the claim's reaper requeues it in 15 minutes,
            # rather than this killing the batch.
            logger.exception("could not record failure for outbox row %s", row.get("id"))
        return "failed"


def drain_outbox(
    sb=None, *, limit: int = DEFAULT_BATCH_LIMIT, chapter_id: str | None = None
) -> dict:
    """Claim up to `limit` pending outbox rows, oldest first, and deliver them.

    `chapter_id` narrows the sweep to one tenant — used by tests and by an
    operator draining a single chapter by hand. The scheduled run passes nothing
    and sweeps every chapter.

    Returns {"processed", "sent", "simulated", "failed"}.
    """
    client = _resolve_sb(sb)
    mode = _global_mode()

    claimed = (
        call_rpc(
            "outbox_claim_batch",
            {"p_limit": limit, "p_chapter_id": chapter_id},
            sb=client,
        ).data
        or []
    )

    counts = {"processed": 0, "sent": 0, "simulated": 0, "failed": 0}
    names: dict = {}  # chapter_id -> name, for the message footer
    for row in claimed:
        status = _deliver_row(client, row, mode=mode, names=names)
        counts["processed"] += 1
        counts[status] = counts.get(status, 0) + 1

    if counts["processed"]:
        logger.info("outbox drain: %s", counts)
    return counts
