"""Tasks HTTP surface. Mounted under `/api/tasks` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import get_current_user
from api.rbac.services.permissions import has_permission
from api.tasks.api.schemas import TaskCreate, TaskStatusUpdate
from api.tasks.auth import TASKS_COMPLETE, TASKS_CREATE, require_permission
from api.tasks.db.session import get_tasks_db
from api.tasks.services import tasks as svc

router = APIRouter()


@router.get("/")
async def list_tasks(status: str | None = None, user=Depends(get_current_user)):
    """List the chapter's tasks. Any authenticated member can view."""
    return svc.list_tasks(get_tasks_db(), chapter_id=user["chapter_id"], status=status)


@router.post("/")
async def create_task(
    body: TaskCreate,
    user=Depends(require_permission(TASKS_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return svc.create_task(
        get_tasks_db(),
        chapter_id=user["chapter_id"],
        title=body.title,
        description=body.description,
        assigned_member_id=body.assigned_member_id,
        group_id=body.group_id,
        event_id=body.event_id,
        required=body.required,
        due_at=body.due_at.isoformat() if body.due_at else None,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/{task_id}/status")
async def update_task_status(
    task_id: str,
    body: TaskStatusUpdate,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Ownership-scoped: tasks:complete covers your OWN task; anyone else's
    requires the tasks:review escalation (see docs/services/permissions-matrix.md)."""
    sb = get_tasks_db()
    task = svc.get_task(sb, chapter_id=user["chapter_id"], task_id=task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    resource = {"owner_member_id": task.get("assigned_member_id")}
    if not has_permission(user, TASKS_COMPLETE, resource=resource, sb=sb):
        raise HTTPException(403, "Missing permission: tasks:complete (or tasks:review for others' tasks)")

    return svc.update_task_status(
        sb,
        chapter_id=user["chapter_id"],
        task_id=task_id,
        status=body.status,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )
