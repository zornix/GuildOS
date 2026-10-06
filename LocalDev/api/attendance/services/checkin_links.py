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
from api.platform.rows import unwrap_row

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


class AmbiguousSession(Exception):
    """More than one attendance session could govern this link."""


def _session_for_link(sb, link: dict) -> dict | None:
    """The attendance session governing this link; ambiguity raises.

    The relation lives on the session side -- attendance_sessions.checkin_link_id
    -> checkin_links.id (0084); a link row carries no session_id. So:

      1. a session bound to THIS link governs it (the normal case: create_session
         opens the link, then records the session pointing at it);
      2. otherwise, if the event has exactly one *still-open* session bound to no
         link at all, it governs (links created before create_checkin_link
         started binding the event's open session to them);
      3. ambiguous → the link is invalid; no session → TTL alone governs.

    The fallback ignores sessions bound to a *different* link, and sessions that
    have already closed: neither has any claim on a link created after it. An
    adopted closed unbound session was #34 -- one stale manual window made every
    freshly generated link 410 on the first scan.
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
            raise AmbiguousSession

    now = datetime.now(timezone.utc)
    unbound = [
        r for r in rows
        if not r.get("checkin_link_id") and not _is_closed(r, now)
    ]
    if len(unbound) == 1:
        return unbound[0]
    if len(unbound) > 1:
        raise AmbiguousSession
    return None


def _is_closed(session: dict, now: datetime) -> bool:
    closes_at = _as_datetime(session.get("closes_at"))
    return closes_at is not None and now > closes_at


def _bind_open_sessions(sb, event_id: str, link_id: str, now: datetime) -> None:
    """Bind the link only when exactly one open unbound session exists.

    Without this, a link made through POST /events/{id}/checkin-link records no
    session at all and _session_for_link has to guess which window governs it.
    Closed sessions are left alone -- binding one would hand the new link the
    dead window it was generated to replace.
    """
    rows = (
        sb.table("attendance_sessions")
        .select("id, closes_at, checkin_link_id")
        .eq("event_id", event_id)
        .execute()
    ).data or []
    unbound = [row for row in rows if not row.get("checkin_link_id") and not _is_closed(row, now)]
    if len(unbound) == 1:
        sb.table("attendance_sessions") \
            .update({"checkin_link_id": link_id}) \
            .eq("id", unbound[0]["id"]) \
            .execute()


async def create_checkin_link(event_id: str, created_by: str, *, sb=None, bind_sessions: bool = True) -> dict:
    """Rotate a link atomically, optionally within the caller's transaction."""
    def create(tx):
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.CHECKIN_LINK_TTL_MINUTES)
        tx.table("checkin_links") \
            .update({"active": False}) \
            .eq("event_id", event_id) \
            .eq("active", True) \
            .execute()
        code = generate_short_code()
        inserted = unwrap_row(tx.table("checkin_links").insert({
            "event_id": event_id,
            "short_code": code,
            "created_by": created_by,
            "expires_at": expires_at.isoformat(),
            "active": True,
        }).execute()) or {}
        if bind_sessions and inserted.get("id"):
            _bind_open_sessions(tx, event_id, inserted["id"], now)
        return {
            "id": inserted.get("id"),
            "short_code": code,
            "url": f"{settings.BASE_URL}/c/{code}",
            "expires_at": expires_at.isoformat(),
            "event_id": event_id,
        }

    if sb is not None:
        return create(sb)

    client = get_db()
    for _ in range(5):
        try:
            with client.transaction() as tx:
                return create(tx)
        except Exception as exc:
            constraint = getattr(getattr(exc, "diag", None), "constraint_name", "") or ""
            if _is_duplicate_code(exc):
                if constraint == "uq_checkin_links_one_active_per_event":
                    raise HTTPException(409, "A check-in code was just created for this event. Refresh to see it.") from exc
                if constraint == "checkin_links_short_code_key" or (
                    not constraint and "checkin_links_short_code_key" in str(exc)
                ):
                    continue
            logger.error("check-in link creation failed for event %s", event_id)
            raise HTTPException(500, "Could not generate check-in code") from exc

    logger.error("check-in code generation exhausted 5 attempts for event %s", event_id)
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

    try:
        session = _session_for_link(sb, link)
    except AmbiguousSession:
        return None
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
