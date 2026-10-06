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

This module sweeps the whole table: oldest pending rows first, small batches within
a time budget,
invoked by Vercel Cron every 5 minutes (GET /api/cron/drain-outbox, authenticated
by CRON_SECRET). It is deliberately cross-chapter — it is a system worker, not a
tenant-scoped request path, and it runs on the admin client.

A batch is *claimed* before anything is delivered: `outbox_claim_batch`
(migrations/0155) flips its rows to 'sending' in the same statement that selects
them, under FOR UPDATE SKIP LOCKED, so two overlapping runs — the 5-minute cron
overtaking a slow batch, or an operator draining one chapter by hand — cannot
both hold the same row and send the same member two messages (issue #32). The
claim also requeues unstamped abandoned claims (over 15 minutes old), refunds
their unused attempts, and parks stamped claims whose delivery outcome is unknown.
Rows past 5 attempts are failed.

Each attempted row advances to a terminal status ('sent', 'simulated' or 'failed'
with `last_error`), unless bookkeeping fails. Rows left unattempted when the time
budget expires stay claimed until the reaper refunds them. No single bad row can
abort the batch. Terminal rows are never claimed again, so a 'failed' row is a
signal for an operator, not something the worker keeps hammering.

Single-row UPDATEs go through the table client rather than a plpgsql RPC: this is
delivery bookkeeping on a non-financial table, not a trust-boundary mutation, and
it matches how every other outbox write in the codebase is done. The claim is the
exception, and has to be: it is one atomic select-and-mark.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from api.announcements.services import twilio_client
from api.auth.notifications import RESET_CODE, SETUP_CODE
from api.platform import message_templates as templates
from api.platform.delivery import delivery_mode, email_delivery_mode
from api.platform.email import send_email
from api.platform.rpc import call_rpc
from api.sms_consent import CONSENT_COLUMNS, has_consent

logger = logging.getLogger(__name__)

DEFAULT_BATCH_LIMIT = 100
# ponytail: fixed budget well under the function timeout; make it a setting if the timeout ever changes.
DRAIN_BUDGET_SECONDS = 45

# Event types whose payload is a live credential (api/auth/notifications.py).
_SECRET_EVENT_TYPES = (SETUP_CODE, RESET_CODE)

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
    """The mode an SMS row is delivered in: the live setting, not the row's.

    `message_outbox.delivery_mode` records what the mode was when the row was
    enqueued; treating it as an override pinned every row queued before the
    twilio flip — and every plpgsql-produced row, which takes 0070's 'dry_run'
    column default — to a simulated delivery forever.
    """
    mode = delivery_mode()
    if mode not in _DISPATCH_MODES:
        # Fail the row loudly: a typo in the Vercel env var must not silently
        # simulate (or silently skip) a message (checklist 2.2). It is read per
        # SMS row, like _email_mode, so a bad SMS setting cannot also stop the
        # email rows — the two channels have separate knobs.
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


def _stamp_provider_attempt(sb, row: dict) -> None:
    """Persist the attempt before calling a provider; ambiguous outcomes are parked."""
    sb.table("message_outbox").update(
        {"provider_attempted_at": _now_iso()}
    ).eq("id", row["id"]).execute()


def _close_row(
    sb, row: dict, *, status: str, last_error: str | None,
    provider_message_id: str | None = None,
) -> None:
    """Move a claimed row from 'sending' to its terminal status.

    `attempts` is not touched here: outbox_claim_batch increments it when it
    hands the row over. The reaper refunds claims that never reached a provider.
    """
    patch = {
        "status": status,
        "last_error": last_error[:1000] if last_error else None,
    }
    if provider_message_id is not None:
        patch["provider_message_id"] = provider_message_id
    if status == "sent":
        patch["delivered_at"] = _now_iso()
    if row["event_type"] in _SECRET_EVENT_TYPES:
        # A finished row must not retain a live credential, including failures.
        # Officers issue a fresh code instead of retrying. payload is NOT NULL.
        patch["payload"] = {}
    sb.table("message_outbox").update(patch).eq("id", row["id"]).execute()
    if status in ("sent", "simulated") and row.get("target_table") in (
        "announcement_sms_sends", "event_notification_sends"
    ):
        # The message is delivered; a bookkeeping failure here must not re-mark it failed.
        try:
            remaining = (
                sb.table("message_outbox").select("id", count="exact")
                .eq("chapter_id", row["chapter_id"])
                .eq("target_table", row["target_table"]).eq("target_id", row["target_id"])
                .in_("status", ["failed", "pending", "sending"]).limit(0).execute()
            )
            if remaining.count == 0:
                sb.table(row["target_table"]).update({"status": "sent"}).eq(
                    "id", row["target_id"]
                ).eq("chapter_id", row["chapter_id"]).execute()
        except Exception:
            logger.exception("could not reconcile parent send log for outbox row %s", row.get("id"))


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


def _deliver_sms(sb, row: dict, *, chapter_name: str, payload: dict) -> str:
    body = templates.render(
        row["event_type"], payload, chapter_name=chapter_name, channel="sms"
    )
    if _global_mode() == DRY_RUN:
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

    _stamp_provider_attempt(sb, row)
    sid = twilio_client.send_sms(phone, body)
    _close_row(sb, row, status="sent", last_error=None, provider_message_id=sid)
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

    _stamp_provider_attempt(sb, row)
    send_email(address, subject, body)
    _close_row(sb, row, status="sent", last_error=None)
    return "sent"


def _deliver_row(sb, row: dict, *, names: dict) -> str:
    """Deliver one row by its channel. Returns its terminal status; never raises.

    Both delivery modes are read per row from settings, so a bad setting fails
    only the rows on that channel.
    """
    try:
        if not row.get("member_id"):
            # Legacy or malformed recipient-less rows cannot be delivered.
            _close_row(sb, row, status="failed", last_error="no recipient")
            return "failed"

        payload = _enrich(sb, row)
        chapter_name = _chapter_name(sb, row["chapter_id"], names)
        if (row.get("channel") or "email") == "sms":
            return _deliver_sms(sb, row, chapter_name=chapter_name, payload=payload)
        return _deliver_email(sb, row, chapter_name=chapter_name, payload=payload)
    except Exception as exc:
        logger.exception("outbox drain failed for row %s", row.get("id"))
        detail = f"{type(exc).__name__}: {exc}"
        try:
            _close_row(sb, row, status="failed", last_error=detail)
        except Exception:
            # Even the bookkeeping write failed (row vanished, DB blip). The row
            # stays 'sending'; the reaper parks stamped rows and refunds unused claims,
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

    started_at = _now_iso()
    started = time.monotonic()
    counts = {"processed": 0, "sent": 0, "simulated": 0, "failed": 0}
    names: dict = {}  # chapter_id -> name, for the message footer
    while counts["processed"] < limit:
        if time.monotonic() - started >= DRAIN_BUDGET_SECONDS:
            break
        claimed = call_rpc(
            "outbox_claim_batch",
            {"p_limit": min(25, limit - counts["processed"]), "p_chapter_id": chapter_id},
            sb=client,
        ).data or []
        if not claimed:
            break
        for row in claimed:
            if time.monotonic() - started >= DRAIN_BUDGET_SECONDS:
                break
            status = _deliver_row(client, row, names=names)
            counts["processed"] += 1
            counts[status] = counts.get(status, 0) + 1

    if chapter_id is None:
        try:
            oldest = (
                client.table("message_outbox").select("created_at")
                .eq("status", "pending").order("created_at").limit(1).execute()
            ).data or []
            finished = datetime.now(timezone.utc)
            age = None
            if oldest:
                created = oldest[0]["created_at"]
                if isinstance(created, str):
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                age = max(0, int((finished - created).total_seconds()))
            client.table("cron_heartbeats").upsert(
                {"job": "drain-outbox", "last_started_at": started_at,
                 "last_finished_at": finished.isoformat(), "last_counts": counts,
                 "oldest_pending_seconds": age}, on_conflict="job"
            ).execute()
        except Exception:
            logger.exception("could not record outbox drain heartbeat")
    if chapter_id is None or counts["processed"]:
        logger.info("outbox drain: %s", counts)
    return counts
