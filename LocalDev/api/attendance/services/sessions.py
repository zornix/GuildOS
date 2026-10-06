"""Attendance sessions — explicit check-in windows over the legacy flow.

A short_link session opens a real check-in link via the existing
api.services.checkin_links machinery (it is NOT reimplemented here), then
records the session row and backfills events.linked_attendance_session_id.
"""

from __future__ import annotations

from fastapi import HTTPException

from api.attendance.services.checkin_links import create_checkin_link
from api.platform.rows import unwrap_row


async def create_session(
    sb,
    *,
    chapter_id: str,
    event_id: str,
    mode: str,
    closes_at: str | None,
    actor_id: str,
) -> dict:
    event = (
        sb.table("events")
        .select("id")
        .eq("id", event_id)
        .eq("chapter_id", chapter_id)
        .maybe_single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")

    with sb.transaction() as tx:
        link = None
        if mode in ("short_link", "qr"):
            # The new session owns this link; do not bind an older manual one.
            link = await create_checkin_link(event_id, actor_id, sb=tx, bind_sessions=False)

        session = unwrap_row(
            tx.table("attendance_sessions")
            .insert({
                "chapter_id": chapter_id,
                "event_id": event_id,
                "mode": mode,
                "closes_at": closes_at,
                "checkin_link_id": link["id"] if link else None,
                "created_by": actor_id,
            })
            .execute()
        )
        # Events↔attendance seam (§7): the event points at its latest session.
        tx.table("events").update({"linked_attendance_session_id": session["id"]}).eq(
            "id", event_id
        ).execute()

    if link:
        session["checkin_link"] = link
    return session


def list_sessions(sb, *, chapter_id: str, event_id: str | None = None) -> list[dict]:
    query = sb.table("attendance_sessions").select("*").eq("chapter_id", chapter_id)
    if event_id:
        query = query.eq("event_id", event_id)
    return query.order("created_at", desc=True).execute().data or []
