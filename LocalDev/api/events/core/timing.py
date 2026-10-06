"""Interpret event date/time in the chapter's local timezone."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "America/Los_Angeles"


def chapter_timezone(sb, chapter_id: str) -> str:
    row = sb.table("chapters").select("timezone").eq("id", chapter_id).maybe_single().execute().data
    name = (row or {}).get("timezone") or DEFAULT_TZ
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return DEFAULT_TZ
    return name


def event_start_utc(event: dict, tz_name: str) -> datetime:
    day = event["date"]
    start = event.get("time")
    if isinstance(day, str):
        day = date.fromisoformat(day)
    if isinstance(start, str):
        start = time.fromisoformat(start)
    start = start or time(23, 59, 59)
    return datetime.combine(day, start).replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)


def has_started(event: dict, tz_name: str, now: datetime) -> bool:
    return event_start_utc(event, tz_name) <= now
