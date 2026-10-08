"""Tasks HTTP surface. Mounted under `/api/tasks` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import get_current_user
from api.rbac.services.permissions import has_permission
from api.tasks.api.jobs import _rpc_http_error
from api.tasks.api.schemas import TaskCreate, TaskStatusUpdate, TaskUpdate
from api.tasks.auth import TASKS_COMPLETE, TASKS_CREATE
from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.tasks.services import tasks as svc
from api.tasks.services.approvals import (
    can_create_event_job,
    can_create_initiative_job,
    can_manage_job,
)

router = APIRouter()


@router.get("/")
def list_tasks(status: str | None = None, user=Depends(get_current_user)):
    """List the chapter's tasks. Any authenticated member can view."""
    return svc.list_tasks(get_db(), chapter_id=user["chapter_id"], status=status)


@router.post("/")
def create_task(
    body: TaskCreate,
    user=Depends(require_permission(TASKS_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    if body.event_id and body.initiative_id:
        raise HTTPException(422, "A job may not be linked to both an event and an initiative")
    # Attaching a job to an event requires running that event (supervisor/organizer)
    # or holding tasks:assign.
    if body.event_id and not can_create_event_job(sb, user=user, event_id=body.event_id):
        raise HTTPException(
            403,
            "Creating a job on this event requires being a supervisor/organizer "
            "of it or holding tasks:assign",
        )
    # Attaching a job to an initiative requires being an assigned chair of it
    # or holding tasks:assign.
    if body.initiative_id and not can_create_initiative_job(
        sb, user=user, initiative_id=body.initiative_id
    ):
        raise HTTPException(
            403,
            "Creating a job on this initiative requires being an assigned chair "
            "of it or holding tasks:assign",
        )
    return svc.create_task(
        sb,
        chapter_id=user["chapter_id"],
        title=body.title,
        description=body.description,
        assigned_member_id=body.assigned_member_id,
        group_id=body.group_id,
        event_id=body.event_id,
        initiative_id=body.initiative_id,
        people_needed=body.people_needed,
        required=body.required,
        due_at=body.due_at.isoformat() if body.due_at else None,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/{task_id}/status")
def update_task_status(
    task_id: str,
    body: TaskStatusUpdate,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Ownership-scoped: tasks:complete covers your OWN task; anyone else's
    requires the tasks:review escalation (see docs/services/permissions-matrix.md)."""
    sb = get_db()
    task = svc.get_task(sb, chapter_id=user["chapter_id"], task_id=task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    committed = bool((
        sb.table("task_commitments").select("id")
        .eq("chapter_id", user["chapter_id"]).eq("task_id", task_id)
        .eq("member_id", user["id"]).eq("status", "active").execute()
    ).data)
    owns_task = task.get("assigned_member_id") == user["id"] or committed
    if not has_permission(user, TASKS_COMPLETE, sb=sb) or not (
        owns_task or has_permission(user, "tasks:review", sb=sb)
    ):
        raise HTTPException(403, "Missing permission: tasks:complete (or tasks:review for others' tasks)")

    try:
        return svc.update_task_status(
            sb,
            chapter_id=user["chapter_id"],
            task_id=task_id,
            status=body.status,
            actor_id=user["id"],
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        message = str(exc)
        for prefix, detail in (
            ("task_closed:", "A closed task cannot change status"),
            ("task_in_review:", "Please approve or reject the reported job"),
            ("job_needs_review:", "Jobs are completed through report and approve"),
        ):
            if prefix in message:
                raise HTTPException(409, detail) from exc
        raise _rpc_http_error(exc) from exc


def _manageable_task_or_error(sb, *, user: dict, task_id: str) -> dict:
    """404 the job, or 403 the caller — the manage gate for edit/cancel."""
    task = svc.get_task(sb, chapter_id=user["chapter_id"], task_id=task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not can_manage_job(sb, user=user, task=task):
        raise HTTPException(403, "You are not authorized to manage this job")
    return task


@router.patch("/{task_id}")
def update_task(
    task_id: str,
    body: TaskUpdate,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Edit a job's own fields. Parent/kind/status are immutable."""
    sb = get_db()
    _manageable_task_or_error(sb, user=user, task_id=task_id)
    try:
        return svc.update_task(
            sb,
            chapter_id=user["chapter_id"],
            task_id=task_id,
            actor_id=user["id"],
            title=body.title,
            description=body.description,
            people_needed=body.people_needed,
            due_at=body.due_at.isoformat() if body.due_at else None,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise _rpc_http_error(exc) from exc


@router.delete("/{task_id}")
def cancel_task(
    task_id: str,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Delete a job = cancel it. Only while it is still in the To-do column."""
    sb = get_db()
    _manageable_task_or_error(sb, user=user, task_id=task_id)
    try:
        return svc.cancel_task(
            sb,
            chapter_id=user["chapter_id"],
            task_id=task_id,
            actor_id=user["id"],
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise _rpc_http_error(exc) from exc
