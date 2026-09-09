"""Task commitments service — volunteer/uncommit via tk_* RPCs, reads + attribution.

Spec §4: open tasks are volunteered for; uncommit is always allowed but logged
(late when < 24h before the linked event's start — resolved decision #1).
"""

from __future__ import annotations

from datetime import date

from api.platform.rpc import call_rpc


def commit_task(
    sb,
    *,
    chapter_id: str,
    task_id: str,
    member_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tk_commit_task",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_member_id": member_id,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def uncommit_task(
    sb,
    *,
    chapter_id: str,
    task_id: str,
    member_id: str,
    actor_id: str,
    reason: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tk_uncommit_task",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_member_id": member_id,
            "p_actor_id": actor_id,
            "p_reason": reason,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


# ── reads ────────────────────────────────────────────────────────────────────


def list_task_commitments(sb, *, chapter_id: str, task_id: str) -> dict:
    """Active commitments plus the full commit/uncommit history for one task."""
    active = (
        sb.table("task_commitments")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("task_id", task_id)
        .eq("status", "active")
        .order("committed_at")
        .execute()
    ).data or []
    history = (
        sb.table("task_commitment_log")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("task_id", task_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    return {"active": active, "history": history}


def uncommit_log(
    sb,
    *,
    chapter_id: str,
    member_id: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """The social-accountability feed: every uncommit, chapter-visible, newest first."""
    query = (
        sb.table("task_commitment_log")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("action", "uncommit")
    )
    if member_id:
        query = query.eq("member_id", member_id)
    return query.order("created_at", desc=True).limit(limit).execute().data or []


def _past_event_ids(sb, *, chapter_id: str, event_ids: list[str]) -> set[str]:
    """Of `event_ids`, the ones that have already happened (chapter-scoped)."""
    if not event_ids:
        return set()
    rows = (
        sb.table("events")
        .select("id")
        .eq("chapter_id", chapter_id)
        .in_("id", event_ids)
        .lte("date", date.today().isoformat())
        .execute()
    ).data or []
    return {str(r["id"]) for r in rows}


def _event_role_counts(sb, *, chapter_id: str, member_id: str) -> tuple[int, int]:
    """(events_organized, events_supervised) — credit only for events that ran.

    Both are computed on read from the join tables the events domain writes:
    `event_organizers` (0100) and `event_supervisors` (0141). Events have no
    completion status, so "happened" is date <= today; a signup for next month
    is a plan, not an attribution. Rows are counted per event (both tables are
    UNIQUE on (event_id, member_id), so a row is one event).
    """
    organizer_rows = (
        sb.table("event_organizers")
        .select("event_id")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .execute()
    ).data or []
    supervisor_rows = (
        sb.table("event_supervisors")
        .select("event_id")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .execute()
    ).data or []

    organized = {str(r["event_id"]) for r in organizer_rows}
    supervised = {str(r["event_id"]) for r in supervisor_rows}
    past = _past_event_ids(
        sb, chapter_id=chapter_id, event_ids=sorted(organized | supervised)
    )
    return len(organized & past), len(supervised & past)


def attribution(sb, *, chapter_id: str, member_id: str, recent_limit: int = 10) -> dict:
    """Per-member attribution ledger (spec §4).

    Counts every structurally-derived contribution: task commitments plus the
    events this member organized or supervised. Positive-only by design — this
    ledger never feeds standing (ADR-0004).
    """
    log_rows = (
        sb.table("task_commitment_log")
        .select("id, task_id, action, late, reason, event_id, hours_before_event, created_at")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []
    completed_rows = (
        sb.table("task_commitments")
        .select("id")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .eq("status", "completed")
        .execute()
    ).data or []

    commits = [r for r in log_rows if r["action"] == "commit"]
    uncommits = [r for r in log_rows if r["action"] == "uncommit"]
    events_organized, events_supervised = _event_role_counts(
        sb, chapter_id=chapter_id, member_id=member_id
    )
    return {
        "member_id": member_id,
        "tasks_committed": len(commits),
        "tasks_completed": len(completed_rows),
        "uncommits": len(uncommits),
        "late_uncommits": sum(1 for r in uncommits if r["late"]),
        "events_organized": events_organized,
        "events_supervised": events_supervised,
        "recent_log": log_rows[:recent_limit],
    }


def active_commitments_by_task(sb, *, chapter_id: str) -> dict[str, list[str]]:
    """task_id -> committed member ids (for list-response summaries)."""
    rows = (
        sb.table("task_commitments")
        .select("task_id, member_id")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .order("committed_at")
        .execute()
    ).data or []
    summary: dict[str, list[str]] = {}
    for row in rows:
        summary.setdefault(str(row["task_id"]), []).append(str(row["member_id"]))
    return summary
