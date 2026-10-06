"""Tasks service — creation/status via tk_* RPCs, reads via the table builder."""

from __future__ import annotations

from api.platform.rpc import call_rpc


def create_task(
    sb,
    *,
    chapter_id: str,
    title: str,
    description: str | None,
    assigned_member_id: str | None,
    group_id: str | None,
    required: bool,
    due_at: str | None,
    actor_id: str,
    event_id: str | None = None,
    initiative_id: str | None = None,
    people_needed: int = 1,
    idempotency_key: str | None = None,
) -> dict:
    with sb.transaction() as tx:
        result = call_rpc(
            "tk_create_task",
            {
                "p_chapter_id": chapter_id,
                "p_title": title,
                "p_description": description,
                "p_assigned_member_id": assigned_member_id,
                "p_group_id": group_id,
                "p_event_id": event_id,
                "p_initiative_id": initiative_id,
                "p_required": required,
                "p_due_at": due_at,
                "p_actor_id": actor_id,
                "p_idempotency_key": idempotency_key,
            },
            sb=tx,
        )
        task = result.data
        # Capacity isn't a param of tk_create_task (0110); set it in a follow-up
        # single-row update (non-trust-boundary column, default 1).
        if people_needed and people_needed != 1 and task:
            (
                tx.table("tasks")
                .update({"people_needed": people_needed})
                .eq("id", task["id"])
                .eq("chapter_id", chapter_id)
                .execute()
            )
            task["people_needed"] = people_needed

    return task


def update_task_status(
    sb,
    *,
    chapter_id: str,
    task_id: str,
    status: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tk_update_task_status",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_status": status,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def update_task(
    sb,
    *,
    chapter_id: str,
    task_id: str,
    actor_id: str,
    title: str | None = None,
    description: str | None = None,
    people_needed: int | None = None,
    due_at: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Edit a job's own fields. NULL = leave that column alone.

    people_needed IS a param here (unlike tk_create_task, which still needs the
    Phase-1 follow-up UPDATE), so there is no second write after this call.
    """
    result = call_rpc(
        "tk_update_task",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_title": title,
            "p_description": description,
            "p_people_needed": people_needed,
            "p_due_at": due_at,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def cancel_task(
    sb,
    *,
    chapter_id: str,
    task_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    """Job delete IS cancel — status='cancelled', row kept, open-only."""
    result = call_rpc(
        "tk_cancel_task",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def get_task(sb, *, chapter_id: str, task_id: str) -> dict | None:
    result = (
        sb.table("tasks")
        .select("*")
        .eq("id", task_id)
        .eq("chapter_id", chapter_id)
        .maybe_single()
        .execute()
    )
    return result.data


def list_tasks(sb, *, chapter_id: str, status: str | None = None) -> list[dict]:
    """Chapter tasks, newest first. Additive V1 fields: every row carries
    event_id (select *) plus a committed_member_ids summary (active commitments)."""
    from api.tasks.services.commitments import active_commitments_by_task

    query = sb.table("tasks").select("*").eq("chapter_id", chapter_id)
    if status:
        query = query.eq("status", status)
    rows = query.order("created_at", desc=True).execute().data or []

    summary = active_commitments_by_task(sb, chapter_id=chapter_id)
    for row in rows:
        claimants = summary.get(str(row["id"]), [])
        row["committed_member_ids"] = claimants
        row["claimants"] = claimants
        row["claimed_count"] = len(claimants)
        row["people_needed"] = row.get("people_needed", 1)
        # Surface the job kind so the frontend can render the security
        # shield variant and filter security jobs out of the Jobs section.
        row["kind"] = row.get("kind", "standard")
    return rows
