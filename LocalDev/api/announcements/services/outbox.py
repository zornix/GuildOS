"""Officer-visible view of `message_outbox` — issue #48.

The drain (api/cron/services/outbox_drain.py) is the writer; this is the read
side plus one operator action. A 'failed' row is terminal for the worker, so
without a retry the only way back into the queue is a manual SQL update.

Bodies are rendered with the same templates the drain uses, so what an officer
reads here is what the member was (or will be) sent. Rendering is best-effort:
a row whose payload no template can render still has to be visible, otherwise
the surface that exists to explain failures hides the worst of them.
"""

from __future__ import annotations

from api.cron.core import templates

LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200


class OutboxRowNotFound(Exception):
    """No such outbox row in this chapter."""


class OutboxRowNotFailed(Exception):
    """Only a failed row can be requeued."""

    def __init__(self, status: str):
        super().__init__(status)
        self.status = status


def _mask_phone(phone: str | None) -> str | None:
    """Last four digits only — officers need to tell recipients apart, not dial."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    return f"•••• {digits[-4:]}" if len(digits) >= 4 else None


# A setup/reset code in the payload is a live credential. Officers can issue
# their own, but the outbox is a different surface with a different reader, so
# the code itself never renders here.
_SECRET_EVENT_TYPES = {"SETUP_CODE", "RESET_CODE"}


def _body(row: dict) -> str:
    if row["event_type"] in _SECRET_EVENT_TYPES:
        return "Account code (hidden)."
    try:
        return templates.render(
            row["event_type"],
            row.get("payload"),
            channel=row.get("channel") or "email",
        )
    except Exception:
        return ""


def list_outbox(
    sb, *, chapter_id: str, status: str | None = None, limit: int = LIST_LIMIT_DEFAULT
) -> list[dict]:
    """Chapter outbox rows, newest first, with masked recipient details."""
    query = (
        sb.table("message_outbox")
        .select("*")
        .eq("chapter_id", chapter_id)
        .order("created_at", desc=True)
        .limit(max(1, min(limit, LIST_LIMIT_MAX)))
    )
    if status:
        query = query.eq("status", status)
    rows = query.execute().data or []

    member_ids = sorted({r["member_id"] for r in rows if r.get("member_id")})
    members: dict[str, dict] = {}
    if member_ids:
        members = {
            m["id"]: m
            for m in (
                sb.table("members")
                .select("id, name, phone")
                .in_("id", member_ids)
                .execute()
            ).data
            or []
        }

    out = []
    for r in rows:
        member = members.get(r.get("member_id")) or {}
        out.append(
            {
                "id": r["id"],
                "event_type": r["event_type"],
                "channel": r.get("channel") or "email",
                "recipient_name": member.get("name"),
                "recipient_phone": _mask_phone(member.get("phone")),
                "body": _body(r),
                "status": r["status"],
                "attempts": r.get("attempts", 0),
                "created_at": r["created_at"],
                "delivered_at": r.get("delivered_at"),
                "error": r.get("last_error"),
            }
        )
    return out


def retry_outbox_row(sb, *, chapter_id: str, row_id: str) -> dict:
    """Put one failed row back in the queue for the next drain.

    attempts resets too: 0155 fails a row for good past 5 attempts, so a retry
    that kept the count would be refused by the very next claim.
    """
    row = (
        sb.table("message_outbox")
        .select("id, status")
        .eq("id", row_id)
        .eq("chapter_id", chapter_id)
        .maybe_single()
        .execute()
    ).data
    if not row:
        raise OutboxRowNotFound(row_id)
    if row["status"] != "failed":
        raise OutboxRowNotFailed(row["status"])

    sb.table("message_outbox").update(
        {"status": "pending", "last_error": None, "attempts": 0, "claimed_at": None}
    ).eq("id", row_id).eq("chapter_id", chapter_id).execute()
    return {"id": row_id, "status": "pending"}
