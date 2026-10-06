"""Announcement SMS — recipient resolution, two-phase confirm, delivery dispatch.

SMS send permission is limited to President and Secretary
(`announcements:send:sms`), every send shows a confirmation step with the
recipient count, and every send is logged with its sender (visible to exec).

Flow:
  1. preview  — resolve the announcement's audience to active members with a
     non-empty phone; the UI shows
     {recipient_count, no_phone_count, no_consent_count}.
  2. send     — the caller re-submits the count it confirmed. If the resolved
     count has drifted, RecipientCountMismatch (HTTP 409) forces the UI to
     re-show the confirmation. Otherwise the atomic `an_send_announcement_sms`
     RPC (0132) writes the append-only send log, one outbox row per recipient,
     and the audit entry.
  3. dispatch — honors settings.MESSAGE_DELIVERY_MODE:
       dry_run (default) — no network; outbox rows are marked 'simulated', which
                           is what actually happened. They are NOT marked 'sent'
                           (GTMLarpChecklist 2.2: the exec SMS log must not render
                           a clean delivery history of messages nobody received).
       twilio            — POST each message to the Twilio REST API via
                           api/announcements/services/twilio_client.py.
     Any other value raises ValueError: one typo in a Vercel env var must not
     silently park every message as 'pending' forever.

Delivery config lives in api/config.py (settings), never os.environ, so it is
part of the settings surface and the production boot guard.

No FastAPI imports here — routes translate the domain exceptions below into
HTTP status codes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from api.platform.rpc import call_rpc
from api.announcements.services import twilio_client
from api.platform import message_templates as templates
from api.platform.delivery import delivery_mode
from api.rbac.services.permissions import is_officer
from api.sms_consent import CONSENT_COLUMNS, has_consent

logger = logging.getLogger(__name__)


class AnnouncementNotFound(Exception):
    """No such announcement in this chapter."""


class AnnouncementNotSent(Exception):
    """SMS requires the in-app feed post first (announcements.status='sent')."""


class RecipientCountMismatch(Exception):
    """Confirmed count is stale; carries the fresh counts for re-confirmation."""

    def __init__(self, recipient_count: int, no_phone_count: int):
        self.recipient_count = recipient_count
        self.no_phone_count = no_phone_count
        super().__init__(
            f"recipient count changed: {recipient_count} SMS-reachable members now"
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _has_phone(member: dict) -> bool:
    return bool((member.get("phone") or "").strip())


def get_announcement(sb, *, chapter_id: str, announcement_id: str) -> dict:
    row = (
        sb.table("announcements")
        .select("*")
        .eq("id", announcement_id)
        .eq("chapter_id", chapter_id)
        .maybe_single()
        .execute()
    ).data
    if not row:
        raise AnnouncementNotFound(announcement_id)
    return row


# ── Recipient resolution ─────────────────────────────────────────────────────


def resolve_recipients(sb, *, chapter_id: str, audience: str) -> dict:
    """Resolve an audience to SMS-reachable members (active + non-empty phone).

    Returns {recipient_member_ids, recipient_count, no_phone_count,
    no_consent_count} where no_phone_count is audience members excluded for
    lacking a phone and no_consent_count those dropped for lacking consent.

    In `twilio` mode an unconsented member is not reachable (#57), so the
    confirmation count the officer approves matches what actually sends;
    `dry_run` still simulates everyone.
    """
    members = (
        sb.table("members")
        .select(f"id, phone, role, {CONSENT_COLUMNS}")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .execute()
    ).data or []

    if audience == "officers":
        # members.role is display-only; permissions come from member_roles via
        # api.rbac. One chapter-wide fetch, then the shared rule per member.
        role_rows = (
            sb.table("member_roles")
            .select("member_id, role_key")
            .eq("chapter_id", chapter_id)
            .execute()
        ).data or []
        keys_by_member: dict[str, set[str]] = {}
        for r in role_rows:
            keys_by_member.setdefault(r["member_id"], set()).add(r["role_key"])
        members = [
            m for m in members if is_officer(m, keys_by_member.get(m["id"], ()))
        ]
    elif audience == "members_with_balance":
        from api.treasury.core.balance import BalanceEngine

        owing = {
            mid for mid, cents in BalanceEngine(sb).outstanding_by_member(chapter_id).items()
            if cents > 0
        }
        members = [m for m in members if m["id"] in owing]
    # default audience 'chapter' = every active member

    with_phone = [m for m in members if _has_phone(m)]
    reachable = (
        [m for m in with_phone if has_consent(m)]
        if delivery_mode() == "twilio"
        else with_phone
    )
    return {
        "recipient_member_ids": [m["id"] for m in reachable],
        "recipient_count": len(reachable),
        "no_phone_count": len(members) - len(with_phone),
        # Otherwise the dropped members are counted nowhere and the officer
        # sees a smaller blast with no reason (#89).
        "no_consent_count": len(with_phone) - len(reachable),
    }


def preview_sms(sb, *, chapter_id: str, announcement_id: str) -> dict:
    """The confirmation-step payload: who would this blast reach right now?"""
    ann = get_announcement(sb, chapter_id=chapter_id, announcement_id=announcement_id)
    resolved = resolve_recipients(sb, chapter_id=chapter_id, audience=ann["audience"])
    return {
        "announcement_id": announcement_id,
        "audience": ann["audience"],
        "recipient_count": resolved["recipient_count"],
        "no_phone_count": resolved["no_phone_count"],
        "no_consent_count": resolved["no_consent_count"],
    }


# ── Two-phase confirmed send ─────────────────────────────────────────────────


def send_announcement_sms(
    sb,
    *,
    chapter_id: str,
    announcement_id: str,
    actor_id: str,
    confirmed_recipient_count: int,
    idempotency_key: str | None = None,
) -> dict:
    ann = get_announcement(sb, chapter_id=chapter_id, announcement_id=announcement_id)
    if ann["status"] != "sent":
        # The in-app feed post comes first; SMS only amplifies it.
        raise AnnouncementNotSent(announcement_id)

    resolved = resolve_recipients(sb, chapter_id=chapter_id, audience=ann["audience"])
    if confirmed_recipient_count != resolved["recipient_count"]:
        raise RecipientCountMismatch(
            resolved["recipient_count"], resolved["no_phone_count"]
        )

    send_row = call_rpc(
        "an_send_announcement_sms",
        {
            "p_chapter_id": chapter_id,
            "p_announcement_id": announcement_id,
            "p_actor_id": actor_id,
            "p_recipient_member_ids": resolved["recipient_member_ids"],
            "p_body_snapshot": ann["body"],
            "p_delivery_mode": delivery_mode(),
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    ).data

    return dispatch_send(sb, send_row)


# ── Delivery dispatch ────────────────────────────────────────────────────────


def dispatch_send(sb, send_row: dict, *, send_table: str = "announcement_sms_sends") -> dict:
    """Deliver a send's pending outbox rows per settings.MESSAGE_DELIVERY_MODE.

    dry_run marks rows 'simulated' without any network call; twilio POSTs to the
    Twilio REST API. An unrecognized mode raises ValueError rather than parking
    the rows silently. Idempotent: already-delivered rows are not re-sent.

    The send-log row itself advances to 'sent'/'failed' — its CHECK constraint
    (0131:20, 0143:23) allows only queued/sent/failed — but it carries its own
    `delivery_mode` column, so a dry_run send reads as "sent, delivery_mode=dry_run"
    and the per-recipient truth lives on the 'simulated' outbox rows.

    send_table names the append-only send-log table the outbox rows target
    (default: announcement_sms_sends). Other domains with their own send-log
    table but the same outbox/dry_run/twilio shape (e.g. events notify's
    event_notification_sends) reuse this dispatcher by passing their table.
    """
    mode = send_row.get("delivery_mode") or delivery_mode()
    candidates = (
        sb.table("message_outbox")
        .select("id")
        .eq("target_table", send_table)
        .eq("target_id", send_row["id"])
        .eq("status", "pending")
        .execute()
    ).data or []
    pending = []
    if candidates:
        # Only rows still pending are returned: the cron may have claimed others.
        pending = (
            sb.table("message_outbox")
            .update({"status": "sending", "claimed_at": _now_iso()})
            .in_("id", [c["id"] for c in candidates])
            .eq("status", "pending")
            .execute()
        ).data or []
    if not pending:
        refreshed = (
            sb.table(send_table).select("*").eq("id", send_row["id"])
            .maybe_single().execute()
        ).data
        return refreshed or send_row

    if mode == "dry_run":
        for row in pending:
            # 'simulated', not 'sent': no network call was made.
            # delivered_at stays NULL — nothing was delivered to time-stamp.
            sb.table("message_outbox").update(
                {"status": "simulated", "last_error": None}
            ).eq("id", row["id"]).execute()
        final_status = "sent"
    elif mode == "twilio":
        chapter = (
            sb.table("chapters")
            .select("name")
            .eq("id", send_row["chapter_id"])
            .maybe_single()
            .execute()
        ).data
        chapter_name = (chapter or {}).get("name") or ""
        statuses = [
            _dispatch_twilio_row(sb, row, chapter_name=chapter_name) for row in pending
        ]
        final_status = "failed" if "failed" in statuses else "sent"
    else:
        raise ValueError(
            f"Unknown MESSAGE_DELIVERY_MODE {mode!r}; expected 'dry_run' or 'twilio'"
        )

    sb.table(send_table).update({"status": final_status}).eq(
        "id", send_row["id"]
    ).execute()
    refreshed = (
        sb.table(send_table)
        .select("*")
        .eq("id", send_row["id"])
        .maybe_single()
        .execute()
    ).data
    return refreshed or {**send_row, "status": final_status}


def _dispatch_twilio_row(sb, row: dict, *, chapter_name: str = "") -> str:
    member = (
        sb.table("members")
        .select(f"id, phone, {CONSENT_COLUMNS}")
        .eq("id", row["member_id"])
        .maybe_single()
        .execute()
    ).data
    phone = ((member or {}).get("phone") or "").strip()
    body = (row.get("payload") or {}).get("body", "")
    last_error: str | None = None

    if phone and not has_consent(member):
        # Same rule as the drain: no prior express consent, no real send (#57).
        # Recorded verbatim so an officer can filter the outbox on it.
        sb.table("message_outbox").update(
            {"status": "failed", "last_error": "no_consent"}
        ).eq("id", row["id"]).execute()
        return "failed"

    try:
        if not phone:
            raise RuntimeError(f"member {row['member_id']} has no phone")
        sb.table("message_outbox").update(
            {"provider_attempted_at": _now_iso()}
        ).eq("id", row["id"]).execute()
        sid = twilio_client.send_sms(phone, f"{body}\n{templates.footer(chapter_name)}")
        status = "sent"
    except Exception:
        # A swallowed, unlogged failure is how "flip to twilio" turns into
        # "every row failed and nobody was told".
        logger.exception(
            "twilio dispatch failed for message_outbox row %s", row.get("id")
        )
        status = "failed"
        last_error = "provider call failed"
    patch = {"status": status, "last_error": last_error}
    if status == "failed":
        patch["provider_attempted_at"] = None
    if status == "sent":
        patch["delivered_at"] = _now_iso()  # only a real send has a delivery time
        if sid is not None:
            patch["provider_message_id"] = sid
    try:
        sb.table("message_outbox").update(patch).eq("id", row["id"]).execute()
    except Exception:
        if status != "sent":
            raise
        logger.exception("could not close delivered message_outbox row %s", row.get("id"))
        # Keep the attempt stamp so Retry finishes bookkeeping without resending.
        sb.table("message_outbox").update(
            {"status": "failed", "last_error": "delivery bookkeeping failed"}
        ).eq("id", row["id"]).execute()
        return "failed"
    return status


# ── Send log (exec visibility) ───────────────────────────────────────────────


def list_sms_log(sb, *, chapter_id: str, limit: int = 50) -> list[dict]:
    """Every SMS send, newest first, with sender attribution."""
    sends = (
        sb.table("announcement_sms_sends")
        .select("*")
        .eq("chapter_id", chapter_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    ).data or []

    titles: dict[str, str] = {}
    announcement_ids = sorted({s["announcement_id"] for s in sends})
    if announcement_ids:
        rows = (
            sb.table("announcements")
            .select("id, title")
            .in_("id", announcement_ids)
            .execute()
        ).data or []
        titles = {r["id"]: r["title"] for r in rows}

    return [
        {
            "id": s["id"],
            "announcement_id": s["announcement_id"],
            "announcement_title": titles.get(s["announcement_id"]),
            "sender_id": s["sender_id"],
            "recipient_count": s["recipient_count"],
            "delivery_mode": s["delivery_mode"],
            "status": s["status"],
            "created_at": s["created_at"],
        }
        for s in sends
    ]
