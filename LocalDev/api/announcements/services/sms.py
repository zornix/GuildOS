"""Announcement SMS — recipient resolution, two-phase confirm, delivery dispatch.

SPEC §6: SMS send permission is limited to President and Secretary
(`announcements:send:sms`), every send shows a confirmation step with the
recipient count, and every send is logged with its sender (visible to exec).

Flow:
  1. preview  — resolve the announcement's audience to active members with a
     non-empty phone; the UI shows {recipient_count, no_phone_count}.
  2. send     — the caller re-submits the count it confirmed. If the resolved
     count has drifted, RecipientCountMismatch (HTTP 409) forces the UI to
     re-show the confirmation. Otherwise the atomic `an_send_announcement_sms`
     RPC (0132) writes the append-only send log, one outbox row per recipient,
     and the audit entry.
  3. dispatch — honors MESSAGE_DELIVERY_MODE:
       dry_run (default) — no network; outbox rows are marked 'sent' locally.
       twilio            — POST each message to the Twilio REST API using
                           TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN /
                           TWILIO_FROM_NUMBER.

TODO(ops): verify A2P 10DLC campaign registration covers application-initiated
announcement SMS before enabling twilio mode.

No FastAPI imports here — routes translate the domain exceptions below into
HTTP status codes.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from api.announcements.db.rpc import call_rpc


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


# Any granular role except plain 'member' marks an officer for the 'officers'
# audience (president, vice_president, treasurer, secretary, chairs, ...).
_NON_OFFICER_ROLE_KEYS = {"member"}


def _delivery_mode() -> str:
    return os.environ.get("MESSAGE_DELIVERY_MODE", "dry_run")


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

    Returns {recipient_member_ids, recipient_count, no_phone_count} where
    no_phone_count is audience members excluded for lacking a phone.
    """
    members = (
        sb.table("members")
        .select("id, phone, role")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .execute()
    ).data or []

    if audience == "officers":
        role_rows = (
            sb.table("member_roles")
            .select("member_id, role_key")
            .eq("chapter_id", chapter_id)
            .execute()
        ).data or []
        rbac_officers = {
            r["member_id"]
            for r in role_rows
            if r["role_key"] not in _NON_OFFICER_ROLE_KEYS
        }
        members = [
            m for m in members if m["role"] == "officer" or m["id"] in rbac_officers
        ]
    elif audience == "members_with_balance":
        accounts = (
            sb.table("member_finance_accounts")
            .select("member_id, outstanding_balance_cents")
            .eq("chapter_id", chapter_id)
            .execute()
        ).data or []
        owing = {
            a["member_id"]
            for a in accounts
            if (a.get("outstanding_balance_cents") or 0) > 0
        }
        members = [m for m in members if m["id"] in owing]
    # default audience 'chapter' = every active member

    reachable = [m for m in members if _has_phone(m)]
    return {
        "recipient_member_ids": [m["id"] for m in reachable],
        "recipient_count": len(reachable),
        "no_phone_count": len(members) - len(reachable),
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
        # The in-app feed post comes first; SMS only amplifies it (SPEC §6).
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
            "p_delivery_mode": _delivery_mode(),
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    ).data

    return dispatch_send(sb, send_row)


# ── Delivery dispatch ────────────────────────────────────────────────────────


def dispatch_send(sb, send_row: dict, *, send_table: str = "announcement_sms_sends") -> dict:
    """Deliver a send's pending outbox rows per MESSAGE_DELIVERY_MODE.

    dry_run marks rows 'sent' without any network call; twilio POSTs to the
    Twilio REST API. Unknown modes leave everything 'queued'/'pending' for an
    external worker. Idempotent: already-delivered rows are not re-sent.

    send_table names the append-only send-log table the outbox rows target
    (default: announcement_sms_sends). Other domains with their own send-log
    table but the same outbox/dry_run/twilio shape (e.g. events notify's
    event_notification_sends) reuse this dispatcher by passing their table.
    """
    mode = send_row.get("delivery_mode") or _delivery_mode()
    pending = (
        sb.table("message_outbox")
        .select("*")
        .eq("target_table", send_table)
        .eq("target_id", send_row["id"])
        .eq("status", "pending")
        .execute()
    ).data or []

    if mode == "dry_run":
        for row in pending:
            sb.table("message_outbox").update(
                {"status": "sent", "delivered_at": _now_iso()}
            ).eq("id", row["id"]).execute()
        final_status = "sent"
    elif mode == "twilio":
        statuses = [_dispatch_twilio_row(sb, row) for row in pending]
        final_status = "failed" if "failed" in statuses else "sent"
    else:
        return send_row

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


def _dispatch_twilio_row(sb, row: dict) -> str:
    member = (
        sb.table("members")
        .select("id, phone")
        .eq("id", row["member_id"])
        .maybe_single()
        .execute()
    ).data
    phone = ((member or {}).get("phone") or "").strip()
    body = (row.get("payload") or {}).get("body", "")
    try:
        if not phone:
            raise RuntimeError(f"member {row['member_id']} has no phone")
        _send_via_twilio(to_number=phone, body=body)
        status = "sent"
    except Exception:
        status = "failed"
    sb.table("message_outbox").update(
        {"status": status, "delivered_at": _now_iso()}
    ).eq("id", row["id"]).execute()
    return status


def _send_via_twilio(*, to_number: str, body: str) -> dict:
    """POST one SMS to the Twilio REST API. Never called in tests (dry_run).

    TODO(ops): verify A2P 10DLC campaign registration covers
    application-initiated announcement SMS before enabling twilio mode.
    """
    import httpx

    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = os.environ["TWILIO_FROM_NUMBER"]

    resp = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
        data={"To": to_number, "From": from_number, "Body": body},
        auth=(account_sid, auth_token),
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


# ── Send log (exec visibility) ───────────────────────────────────────────────


def list_sms_log(sb, *, chapter_id: str, limit: int = 50) -> list[dict]:
    """Every SMS send, newest first, with sender attribution (SPEC §6)."""
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
