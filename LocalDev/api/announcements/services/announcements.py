"""Announcements service — drafts via the table builder, send via an_* RPC."""

from __future__ import annotations

from api.announcements.db.rpc import call_rpc
from api.rbac.db.repositories.member_roles import list_member_role_keys

# Audience values (0086 CHECK): 'chapter' reaches every active member,
# 'officers' every role-holder above plain member, 'members_with_balance'
# everyone the treasury shows owing. Kept in step with sms.resolve_recipients,
# which resolves the same audiences for the SMS blast.
AUDIENCE_CHAPTER = "chapter"
AUDIENCE_OFFICERS = "officers"
AUDIENCE_MEMBERS_WITH_BALANCE = "members_with_balance"

# Any granular role except plain 'member' marks an officer (sms.py mirrors this).
_NON_OFFICER_ROLE_KEYS = {"member"}


def create_draft(
    sb,
    *,
    chapter_id: str,
    title: str,
    body: str,
    audience: str,
    actor_id: str,
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
            }
        )
        .execute()
    )
    data = result.data
    return data[0] if isinstance(data, list) else data


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

    # member_roles only: 0147 backfilled legacy members.role='officer' accounts
    # into it, so officer-audience membership no longer reads members.role
    # (matches sms.resolve_recipients).
    role_keys = set(
        list_member_role_keys(sb, chapter_id=chapter_id, member_id=viewer["id"])
    )
    if role_keys - _NON_OFFICER_ROLE_KEYS:
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
