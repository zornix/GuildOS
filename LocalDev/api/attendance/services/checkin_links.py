"""
Short link generation + validation for event check-in.

Anti-cheat mechanism:
- Officer taps "Open Check-In" -> generates a short-lived link like:
    https://fraternityos.vercel.app/c/A7x9Kp
- Link is valid for N minutes (default 10), displayed on officer's phone
- Members physically present open the link on their own phone
- Link resolves to a check-in page that auto-submits with their session
- After TTL expires, link is dead -- no forwarding after the fact

Anti-forwarding measures:
1. Short TTL (configurable, default 10 min)
2. Officer can manually kill the link early -- within their own chapter only
3. The owning attendance session's closes_at is honored: a closed session's
   link is dead even if its TTL has not run out
4. Audit log shows check-in timestamps for manual review
"""

import logging
import secrets
import string
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException

from api.config import settings
from api.platform.db import get_db

try:  # psycopg2 is the offline/local driver; guarded for supabase-only installs.
    from psycopg2 import errors as _pg_errors
except ImportError:  # pragma: no cover - supabase-only path
    _pg_errors = None

logger = logging.getLogger(__name__)

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 6

# Postgres SQLSTATE for unique_violation -- the only insert failure that means
# "this random code is already taken".
_UNIQUE_VIOLATION = "23505"


def generate_short_code() -> str:
    """Generate a 6-char alphanumeric code. ~56 billion possibilities."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


def _is_duplicate_code(exc: Exception) -> bool:
    """True only for a unique-key collision on the generated short_code.

    The two clients raise this differently: the offline psycopg2 shim
    (api/platform/postgres.py) lets `psycopg2.errors.UniqueViolation` through
    untouched, while supabase-py wraps PostgREST's response in an APIError
    carrying `code='23505'`. Anything else -- a dropped connection, a NOT NULL
    violation, a bad payload -- must NOT be swallowed as a collision: the old
    bare `except Exception: continue` turned every real fault into a misleading
    "Failed to generate unique check-in code" after five silent retries.
    """
    if _pg_errors is not None and isinstance(exc, _pg_errors.UniqueViolation):
        return True
    if getattr(exc, "pgcode", None) == _UNIQUE_VIOLATION:
        return True
    if getattr(exc, "code", None) == _UNIQUE_VIOLATION:
        return True
    # APIError stringifies to its payload dict; details/message carry the code.
    haystack = f"{exc} {getattr(exc, 'details', '') or ''} {getattr(exc, 'message', '') or ''}"
    return _UNIQUE_VIOLATION in haystack or "duplicate key value" in haystack


def _as_datetime(value) -> datetime | None:
    """Coerce a timestamptz to an aware datetime (shim yields datetime, PostgREST str)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _session_for_link(sb, link: dict) -> dict | None:
    """The attendance session governing this link, or None when it is ambiguous.

    The relation lives on the session side -- attendance_sessions.checkin_link_id
    -> checkin_links.id (0084); a link row carries no session_id. So:

      1. a session bound to THIS link governs it (the normal case: create_session
         opens the link, then records the session pointing at it);
      2. otherwise, if the event has exactly one session and that session is
         bound to no link at all, it governs (a link opened directly through
         POST /events/{id}/checkin-link under a manual session);
      3. otherwise None -- ambiguous, and a guess here would either kill a valid
         link or honor the wrong window.

    The fallback deliberately ignores sessions bound to a *different* link, so an
    old closed session cannot kill the fresh link an officer just opened.
    """
    link_id = link.get("id")
    event_id = link.get("event_id")
    if not event_id:
        return None

    rows = (
        sb.table("attendance_sessions")
        .select("id, closes_at, checkin_link_id")
        .eq("event_id", event_id)
        .execute()
    ).data or []

    if link_id:
        bound = [r for r in rows if str(r.get("checkin_link_id") or "") == str(link_id)]
        if len(bound) == 1:
            return bound[0]
        if bound:
            return None

    unbound = [r for r in rows if not r.get("checkin_link_id")]
    if len(unbound) == 1:
        return unbound[0]
    return None


async def create_checkin_link(event_id: str, created_by: str) -> dict:
    """
    Create a new short-lived check-in link for an event.
    Deactivates any existing active link for the same event.
    """
    sb = get_db()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.CHECKIN_LINK_TTL_MINUTES)

    sb.table("checkin_links") \
        .update({"active": False}) \
        .eq("event_id", event_id) \
        .eq("active", True) \
        .execute()

    for _ in range(5):
        code = generate_short_code()
        try:
            sb.table("checkin_links").insert({
                "event_id": event_id,
                "short_code": code,
                "created_by": created_by,
                "expires_at": expires_at.isoformat(),
                "active": True,
            }).execute()

            return {
                "short_code": code,
                "url": f"{settings.BASE_URL}/c/{code}",
                "expires_at": expires_at.isoformat(),
                "event_id": event_id,
            }
        except Exception as exc:
            if _is_duplicate_code(exc):
                continue
            logger.exception("check-in link insert failed for event %s", event_id)
            raise HTTPException(500, "Could not generate check-in code") from exc

    logger.error(
        "check-in code generation exhausted 5 attempts for event %s -- a collision "
        "rate this high means the code space or the table is wrong",
        event_id,
    )
    raise HTTPException(500, "Could not generate check-in code")


async def validate_checkin_link(short_code: str) -> dict | None:
    """Validate a short code. Returns link+event data if valid, None if expired/invalid.

    Three gates: the link is active, its TTL has not run out, and the attendance
    session governing it (when resolvable) has not closed. The session gate is
    the whole reason closes_at exists -- it was written by create_session and
    read by nothing, so "close check-in" left every outstanding link live.

    On success the resolved session is attached as `attendance_session` so
    callers need not look it up again.
    """
    sb = get_db()
    now = datetime.now(timezone.utc)

    result = (
        sb.table("checkin_links")
        .select("*, events(*)")
        .eq("short_code", short_code)
        .eq("active", True)
        .gte("expires_at", now.isoformat())
        .single()
        .execute()
    )

    link = result.data
    if not link:
        return None

    session = _session_for_link(sb, link)
    if session:
        closes_at = _as_datetime(session.get("closes_at"))
        if closes_at is not None and now > closes_at:
            return None

    link["attendance_session"] = session
    return link


async def get_active_link_for_event(event_id: str) -> dict | None:
    """Return the currently active, non-expired link for an event (or None)."""
    sb = get_db()
    now = datetime.now(timezone.utc)
    result = (
        sb.table("checkin_links")
        .select("event_id, short_code, expires_at, active")
        .eq("event_id", event_id)
        .eq("active", True)
        .gte("expires_at", now.isoformat())
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    return {
        "short_code": row["short_code"],
        "url": f"{settings.BASE_URL}/c/{row['short_code']}",
        "expires_at": row["expires_at"],
        "event_id": row["event_id"],
    }


async def list_active_links_for_chapter(chapter_id: str) -> list[dict]:
    """Return all active, non-expired check-in links for events in a chapter.

    The chapter filter is applied in the query (checkin_links.chapter_id exists
    since 0146). This used to fetch every chapter's active links and drop the
    foreign ones in Python -- a tenant leak one missing `continue` wide.
    """
    sb = get_db()
    now = datetime.now(timezone.utc)
    result = (
        sb.table("checkin_links")
        .select("event_id, short_code, expires_at, events(title, date, chapter_id)")
        .eq("chapter_id", chapter_id)
        .eq("active", True)
        .gte("expires_at", now.isoformat())
        .execute()
    )
    rows = []
    for row in result.data or []:
        ev = row.get("events") or {}
        if not ev:
            continue
        rows.append({
            "event_id": row["event_id"],
            "event_title": ev.get("title", ""),
            "date": ev.get("date", ""),
            "short_code": row["short_code"],
            "url": f"{settings.BASE_URL}/c/{row['short_code']}",
            "expires_at": row["expires_at"],
        })
    return rows


async def deactivate_checkin_link(event_id: str, chapter_id: str):
    """Officer manually kills the link before TTL expires.

    chapter_id is required and filtered on: without it, any officer could kill
    any chapter's live check-in link with a guessed event id.
    """
    sb = get_db()
    sb.table("checkin_links") \
        .update({"active": False}) \
        .eq("event_id", event_id) \
        .eq("chapter_id", chapter_id) \
        .eq("active", True) \
        .execute()
