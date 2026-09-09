"""Announcements service — drafts via the table builder, send via an_* RPC."""

from __future__ import annotations

from api.platform.rpc import call_rpc
from api.rbac.db.repositories.member_roles import list_member_role_keys
from api.rbac.services.permissions import is_officer
from api.platform.rows import unwrap_row

# Audience values (0086 CHECK): 'chapter' reaches every active member,
# 'officers' every role-holder above plain member, 'members_with_balance'
# everyone the treasury shows owing. Kept in step with sms.resolve_recipients,
# which resolves the same audiences for the SMS blast.
AUDIENCE_CHAPTER = "chapter"
AUDIENCE_OFFICERS = "officers"
AUDIENCE_MEMBERS_WITH_BALANCE = "members_with_balance"


class AnnouncementNotFound(Exception):
    """No such announcement in this chapter (404, no cross-tenant existence leak)."""


def create_draft(
    sb,
    *,
    chapter_id: str,
    title: str,
    body: str,
    audience: str,
    actor_id: str,
    calendar_date: str | None = None,
    calendar_time: str | None = None,
) -> dict:
    # Single-row, chapter-scoped insert. The trust-boundary mutation is `send`
    # (RPC, atomic outbox enqueue + audit); draft creation stays a plain write.
    result = (
        sb.table("announcements")
        .insert(
            {
                "chapter_id": chapter_id,
                "title": title,
                "body": body,
                "audience": audience,
                "status": "draft",
                "created_by": actor_id,
                # D15: calendar slot, not a send time. Both stay NULL for the
                # plain feed post every existing caller creates.
                "calendar_date": calendar_date,
                "calendar_time": calendar_time,
            }
        )
        .execute()
    )
    return unwrap_row(result)


def hide_from_calendar(sb, *, chapter_id: str, announcement_id: str) -> dict:
    """DELETE semantics for an announcement.

    A draft was never news — the row is removed outright. A *sent* one already
    reached the feed and possibly SMS, so it is only retired from the calendar
    (hidden_from_calendar=TRUE); the sms log and the feed post are untouched.
    Idempotent: hiding an already-hidden row is a no-op 200.
    """
    row = (
        sb.table("announcements")
        .select("id, status, hidden_from_calendar")
        .eq("id", announcement_id)
        .eq("chapter_id", chapter_id)
        .maybe_single()
        .execute()
    ).data
    if not row:
        raise AnnouncementNotFound(f"Announcement {announcement_id} not found")

    if row["status"] == "draft":
        (
            sb.table("announcements")
            .delete()
            .eq("id", announcement_id)
            .eq("chapter_id", chapter_id)
            .execute()
        )
        return {"id": announcement_id, "deleted": True, "hidden_from_calendar": False}

    (
        sb.table("announcements")
        .update({"hidden_from_calendar": True})
        .eq("id", announcement_id)
        .eq("chapter_id", chapter_id)
        .execute()
    )
    return {"id": announcement_id, "deleted": False, "hidden_from_calendar": True}


def send_announcement(
    sb,
    *,
    chapter_id: str,
    announcement_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "an_send_announcement",
        {
            "p_chapter_id": chapter_id,
            "p_announcement_id": announcement_id,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def audiences_for_viewer(sb, *, chapter_id: str, viewer: dict) -> set[str]:
    """The audience values whose recipient set contains this member.

    Mirrors sms.resolve_recipients minus the phone requirement (the in-app feed
    reaches members without a phone), so what a member reads in the feed matches
    what a blast would have sent them.
    """
    audiences = {AUDIENCE_CHAPTER}

    # rbac.is_officer, the same union authorization resolves from: an officer who
    # holds only the legacy members.role reads officers-only notices in the feed.
    role_keys = list_member_role_keys(sb, chapter_id=chapter_id, member_id=viewer["id"])
    if is_officer(viewer, role_keys):
        audiences.add(AUDIENCE_OFFICERS)

    account = (
        sb.table("member_finance_accounts")
        .select("outstanding_balance_cents")
        .eq("chapter_id", chapter_id)
        .eq("member_id", viewer["id"])
        .execute()
    ).data or []
    if any((row.get("outstanding_balance_cents") or 0) > 0 for row in account):
        audiences.add(AUDIENCE_MEMBERS_WITH_BALANCE)

    return audiences


def list_announcements(
    sb,
    *,
    chapter_id: str,
    status: str | None = None,
    viewer: dict | None = None,
    include_drafts: bool = False,
) -> list[dict]:
    """The chapter feed.

    `include_drafts` (announcements:create holders) keeps the full management
    view and honors the `status` filter. Everyone else gets only announcements
    that were actually sent AND whose audience includes them — an unsent draft
    is not chapter news, and an officers-only notice is not everyone's.
    """
    query = sb.table("announcements").select("*").eq("chapter_id", chapter_id)
    if include_drafts:
        if status:
            query = query.eq("status", status)
        return query.order("created_at", desc=True).execute().data or []

    rows = (
        query.eq("status", "sent").order("created_at", desc=True).execute().data or []
    )
    if viewer is None:
        return []
    audiences = audiences_for_viewer(sb, chapter_id=chapter_id, viewer=viewer)
    return [row for row in rows if (row.get("audience") or AUDIENCE_CHAPTER) in audiences]
