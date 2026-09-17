"""Events' outbox enqueue helpers — automatic event email (ADR-0005).

Two events, both email:

  EVENT_CREATED        every active member of the chapter, when a
                       chapter-visible event is created. Payload: title, date,
                       time, location.
  EVENT_ROLE_ASSIGNED  the member an officer assigned as organizer or
                       supervisor. Payload: title, date, role.

The manual "Notify members" SMS blast is a different thing entirely and stays in
api/events/services/notifications.py — that one is officer-triggered, gated on
event completeness, and carries the carrier consent rules.

Removal sends nothing: telling someone they are off a list they never asked to
be on is noise. A member who volunteers themselves as organizer gets no mail
either — they just did it.
"""

from __future__ import annotations

import logging

from api.platform.outbox import enqueue

logger = logging.getLogger(__name__)

EVENT_CREATED = "EVENT_CREATED"
EVENT_ROLE_ASSIGNED = "EVENT_ROLE_ASSIGNED"


def _enqueue(sb, **kwargs) -> dict | None:
    """Queue one event email. A notification failure never fails the write that
    produced it — the event exists whether or not the mail was queued."""
    try:
        return enqueue(sb, channel="email", target_table="events", **kwargs)
    except Exception:
        logger.warning("could not enqueue %s", kwargs.get("event_type"), exc_info=True)
        return None


def notify_event_created(sb, *, chapter_id: str, event: dict) -> int:
    """Fan out EVENT_CREATED to every active member, chapter-visible events
    only. An 'officer'/'custom'/'private' event would otherwise mail its title,
    date and location to people who cannot even see it. Returns rows enqueued."""
    if (event.get("visibility") or "chapter") != "chapter":
        return 0

    members = (
        sb.table("members")
        .select("id")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .execute()
    ).data or []

    payload = {
        "title": event.get("title"),
        "date": str(event.get("date") or ""),
        "time": str(event.get("time") or ""),
        "location": event.get("location"),
    }
    event_id = event["id"]
    queued = 0
    for member in members:
        row = _enqueue(
            sb,
            event_type=EVENT_CREATED,
            chapter_id=chapter_id,
            member_id=member["id"],
            target_id=event_id,
            dedup_key=f"{EVENT_CREATED}:{event_id}:{member['id']}",
            payload=payload,
        )
        queued += 1 if row else 0
    return queued


def notify_role_assigned(
    sb, *, chapter_id: str, event: dict, member_id: str, role: str
) -> dict | None:
    """EVENT_ROLE_ASSIGNED for one member. `role` is 'organizer'|'supervisor'."""
    event_id = event["id"]
    return _enqueue(
        sb,
        event_type=EVENT_ROLE_ASSIGNED,
        chapter_id=chapter_id,
        member_id=member_id,
        target_id=event_id,
        dedup_key=f"{EVENT_ROLE_ASSIGNED}:{event_id}:{member_id}:{role}",
        payload={
            "title": event.get("title"),
            "date": str(event.get("date") or ""),
            "role": role,
        },
    )
