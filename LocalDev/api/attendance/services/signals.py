"""Attendance → treasury/standing signal seam (§7).

Absence-driven fines are issued through POST /api/fines/issue; that path is
authoritative and is not duplicated here. This module exposes the read-side
absence signal for standing derivation (memberadmin) and announcements audiences.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api.events.core.timing import chapter_timezone, has_started


def attendance_summary(
    sb, *, chapter_id: str, member_id: str | None = None, now: datetime | None = None
) -> list[dict]:
    """Derived attendance % over REQUIRED past events.

    For each active member: attended_required, total_required_past_events, and
    attendance_pct (None when the chapter has no required past events).
    Counts required events that have started in the chapter timezone; attended means an
    attendance row with checked_in=true.
    """
    now = now or datetime.now(timezone.utc)
    tz = chapter_timezone(sb, chapter_id)

    members_q = (
        sb.table("members")
        .select("id, name")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
    )
    if member_id:
        members_q = members_q.eq("id", member_id)
    members = members_q.execute().data or []

    events = (
        sb.table("events")
        .select("id, date, time")
        .eq("chapter_id", chapter_id)
        .eq("required", True)
        .lte("date", (now.astimezone(timezone.utc) + timedelta(days=1)).date().isoformat())
        .execute()
    ).data or []
    events = [e for e in events if has_started(e, tz, now)]
    event_ids = [e["id"] for e in events]
    total = len(event_ids)

    attended_by: dict[str, set[str]] = {}
    if event_ids:
        attendance = (
            sb.table("attendance")
            .select("member_id, event_id, checked_in")
            .in_("event_id", event_ids)
            .execute()
        ).data or []
        for a in attendance:
            if a.get("checked_in"):
                attended_by.setdefault(a["member_id"], set()).add(a["event_id"])

    out = []
    for m in members:
        attended = len(attended_by.get(m["id"], ()))
        out.append(
            {
                "member_id": m["id"],
                "name": m["name"],
                "attended_required": attended,
                "total_required_past_events": total,
                "attendance_pct": round(attended / total * 100, 1) if total else None,
            }
        )
    return out


def list_unexcused_absences(sb, *, chapter_id: str, event_id: str) -> list[dict]:
    """Members of the chapter with neither a check-in nor an approved excuse.

    TODO(attendance): once standing derivation consumes this, consider a
    DB-side view to avoid the three-query fan-in (same shape as the roster
    endpoint and POST /api/fines/issue use today).
    """
    members = (
        sb.table("members")
        .select("id, name")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .execute()
    ).data or []
    attendance = (
        sb.table("attendance")
        .select("member_id, checked_in")
        .eq("event_id", event_id)
        .execute()
    ).data or []
    excuses = (
        sb.table("excuses")
        .select("member_id, status")
        .eq("event_id", event_id)
        .execute()
    ).data or []

    checked_in = {a["member_id"] for a in attendance if a.get("checked_in")}
    excused = {e["member_id"] for e in excuses if e.get("status") == "approved"}

    return [
        {"member_id": m["id"], "name": m["name"], "event_id": event_id}
        for m in members
        if m["id"] not in checked_in and m["id"] not in excused
    ]
