"""Contribution record — derived by query from rows that already exist.

Everything here is structurally known (ADR-0004 / CONTEXT.md "Contribution"):
organizer and supervisor rows, chair rows, approved jobs the member committed
to, and check-ins. Nothing is manually awarded, nothing is stored, and no
count ever leaves this module for the standing computation.

No FastAPI imports — the route layer maps errors.
"""

from __future__ import annotations

from collections import Counter


class MemberNotFound(Exception):
    """Member missing, or not in the caller's chapter (no existence leak)."""


def _ids(rows: list[dict], col: str) -> list[str]:
    return sorted({str(r[col]) for r in rows if r.get(col)})


def _as_date(value):
    """`date`/`datetime` → `date`; anything else (None, str) passes through."""
    return value.date() if hasattr(value, "date") else value


def _attendee_counts(sb, event_ids: list[str]) -> Counter:
    """Checked-in attendance rows per event. Counted in Python — the query
    builder has no GROUP BY, and an event's check-in list is small."""
    if not event_ids:
        return Counter()
    rows = (
        sb.table("attendance")
        .select("event_id")
        .in_("event_id", event_ids)
        .eq("checked_in", True)
        .execute()
    ).data or []
    return Counter(str(r["event_id"]) for r in rows)


def _events(sb, chapter_id: str, event_ids: list[str]) -> list[dict]:
    """Event rows (chapter-scoped) decorated with their attendee counts."""
    if not event_ids:
        return []
    rows = (
        sb.table("events")
        .select("id, title, date")
        .eq("chapter_id", chapter_id)
        .in_("id", event_ids)
        .order("date", desc=True)
        .execute()
    ).data or []
    counts = _attendee_counts(sb, [str(r["id"]) for r in rows])
    return [
        {
            "event_id": str(r["id"]),
            "title": r["title"],
            "date": r["date"],
            "attendee_count": counts.get(str(r["id"]), 0),
        }
        for r in rows
    ]


def _member_event_ids(sb, table: str, chapter_id: str, member_id: str) -> list[str]:
    rows = (
        sb.table(table)
        .select("event_id")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .execute()
    ).data or []
    return _ids(rows, "event_id")


def _initiatives_chaired(sb, chapter_id: str, member_id: str) -> list[dict]:
    chair_rows = (
        sb.table("initiative_chairs")
        .select("initiative_id")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .execute()
    ).data or []
    initiative_ids = _ids(chair_rows, "initiative_id")
    if not initiative_ids:
        return []
    rows = (
        sb.table("initiatives")
        .select("id, title, date, end_date")
        .eq("chapter_id", chapter_id)
        .in_("id", initiative_ids)
        .order("date", desc=True)
        .execute()
    ).data or []
    return [
        {
            "initiative_id": str(r["id"]),
            "title": r["title"],
            "date_range": {"start": r["date"], "end": r.get("end_date")},
        }
        for r in rows
    ]


def _jobs_done(sb, chapter_id: str, member_id: str) -> list[dict]:
    """Approved jobs the member committed to. An uncommitted row never counts;
    the approval lives on the task, so the job is 'done' only once approved."""
    commitments = (
        sb.table("task_commitments")
        .select("task_id")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .in_("status", ["active", "completed"])
        .execute()
    ).data or []
    task_ids = _ids(commitments, "task_id")
    if not task_ids:
        return []
    rows = (
        sb.table("tasks")
        .select("id, title, event_id, initiative_id, approved_at")
        .eq("chapter_id", chapter_id)
        .eq("status", "approved")
        .in_("id", task_ids)
        .order("approved_at", desc=True)
        .execute()
    ).data or []
    return [
        {
            "job_id": str(r["id"]),
            "title": r["title"],
            "attached_to": (
                "event" if r.get("event_id")
                else "initiative" if r.get("initiative_id")
                else "standalone"
            ),
            "date": _as_date(r.get("approved_at")),
        }
        for r in rows
    ]


def _events_attended_count(sb, chapter_id: str, member_id: str) -> int:
    """Check-ins. `attendance` has no chapter_id column, so the member's
    chapter (already validated by the caller) is the scope."""
    rows = (
        sb.table("attendance")
        .select("id")
        .eq("member_id", member_id)
        .eq("checked_in", True)
        .execute()
    ).data or []
    return len(rows)


def get_record(sb, *, chapter_id: str, member_id: str) -> dict:
    """The member's contribution record. Raises MemberNotFound off-chapter."""
    member = (
        sb.table("members")
        .select("id")
        .eq("id", member_id)
        .eq("chapter_id", chapter_id)
        .maybe_single()
        .execute()
    ).data
    if not member:
        raise MemberNotFound("Member not found")

    return {
        "member_id": str(member_id),
        "events_organized": _events(
            sb, chapter_id, _member_event_ids(sb, "event_organizers", chapter_id, member_id)
        ),
        "events_supervised": _events(
            sb, chapter_id, _member_event_ids(sb, "event_supervisors", chapter_id, member_id)
        ),
        "initiatives_chaired": _initiatives_chaired(sb, chapter_id, member_id),
        "jobs_done": _jobs_done(sb, chapter_id, member_id),
        "events_attended_count": _events_attended_count(sb, chapter_id, member_id),
    }
