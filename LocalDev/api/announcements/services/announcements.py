"""Announcements service — drafts via the table builder, send via an_* RPC."""

from __future__ import annotations

from api.announcements.db.rpc import call_rpc


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


def list_announcements(sb, *, chapter_id: str, status: str | None = None) -> list[dict]:
    query = sb.table("announcements").select("*").eq("chapter_id", chapter_id)
    if status:
        query = query.eq("status", status)
    return query.order("created_at", desc=True).execute().data or []
