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

    checkin_link_id = None
    link = None
    if mode in ("short_link", "qr"):
        # qr mode renders the same short link as a QR code client-side.
        link = await create_checkin_link(event_id, actor_id)
        link_row = (
            sb.table("checkin_links")
            .select("id")
            .eq("short_code", link["short_code"])
            .maybe_single()
            .execute()
        )
        checkin_link_id = link_row.data["id"] if link_row.data else None

    session = unwrap_row(
        sb.table("attendance_sessions")
        .insert(
            {
                "chapter_id": chapter_id,
                "event_id": event_id,
                "mode": mode,
                "closes_at": closes_at,
                "checkin_link_id": checkin_link_id,
                "created_by": actor_id,
            }
        )
        .execute()
    )

    # Events↔attendance seam (§7): the event points at its latest session.
    sb.table("events").update({"linked_attendance_session_id": session["id"]}).eq(
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
