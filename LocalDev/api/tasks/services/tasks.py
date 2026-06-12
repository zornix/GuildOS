"""Tasks service — creation/status via tk_* RPCs, reads via the table builder."""

from __future__ import annotations

from api.tasks.db.rpc import call_rpc


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
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tk_create_task",
        {
            "p_chapter_id": chapter_id,
            "p_title": title,
            "p_description": description,
            "p_assigned_member_id": assigned_member_id,
            "p_group_id": group_id,
            "p_required": required,
            "p_due_at": due_at,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


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
    query = sb.table("tasks").select("*").eq("chapter_id", chapter_id)
    if status:
        query = query.eq("status", status)
    return query.order("created_at", desc=True).execute().data or []


def incomplete_required_tasks(sb, *, chapter_id: str) -> list[dict]:
    """Cross-service seam (§7): incomplete-required-task signals for standing
    and announcements. Consumers read this; they do not re-query tasks."""
    return (
        sb.table("tasks")
        .select("id, assigned_member_id, title, due_at, status")
        .eq("chapter_id", chapter_id)
        .eq("required", True)
        .in_("status", ["open", "in_progress"])
        .execute()
    ).data or []
