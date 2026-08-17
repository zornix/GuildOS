"""Task commitments HTTP surface — volunteering, the uncommit log, attribution.

Mounted under `/api/tasks` by router.py (before the generic task routes so the
literal `uncommit-log` / `attribution` segments win over `/{task_id}/...`).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.dependencies import get_current_user
from api.rbac.services.permissions import has_permission
from api.tasks.api.schemas import CommitRequest, UncommitRequest
from api.tasks.auth import TASKS_ASSIGN, TASKS_REVIEW
from api.platform.db import get_db
from api.tasks.services import commitments as svc

router = APIRouter()


def _rpc_http_error(exc: Exception) -> HTTPException:
    """Map tk_* RPC exceptions onto HTTP statuses (handlers stay thin)."""
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(404, msg)
    if (
        "active commitment" in msg
        or "cannot be committed" in msg
        or "job_full" in msg
        or "unclaim_locked" in msg
    ):
        return HTTPException(409, msg)
    return HTTPException(400, msg)


@router.post("/{task_id}/commit")
async def commit_task(
    task_id: str,
    body: CommitRequest | None = None,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Self-commit for any authenticated member; committing someone else
    requires tasks:assign."""
    sb = get_db()
    member_id = (body.member_id if body else None) or user["id"]
    if member_id != user["id"] and not has_permission(user, TASKS_ASSIGN, sb=sb):
        raise HTTPException(403, "Missing permission: tasks:assign (required to commit another member)")

    try:
        return svc.commit_task(
            sb,
            chapter_id=user["chapter_id"],
            task_id=task_id,
            member_id=member_id,
            actor_id=user["id"],
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # plpgsql guard violations surface as client errors
        raise _rpc_http_error(exc) from exc


@router.post("/{task_id}/uncommit")
async def uncommit_task(
    task_id: str,
    body: UncommitRequest | None = None,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Always allowed (no hard lock — spec §4); the response carries `late` and
    `hours_before_event`. Uncommitting someone else requires tasks:review."""
    sb = get_db()
    member_id = (body.member_id if body else None) or user["id"]
    if member_id != user["id"] and not has_permission(user, TASKS_REVIEW, sb=sb):
        raise HTTPException(403, "Missing permission: tasks:review (required to uncommit another member)")

    try:
        return svc.uncommit_task(
            sb,
            chapter_id=user["chapter_id"],
            task_id=task_id,
            member_id=member_id,
            actor_id=user["id"],
            reason=body.reason if body else None,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise _rpc_http_error(exc) from exc


@router.get("/uncommit-log")
async def get_uncommit_log(
    member_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(get_current_user),
):
    """Visible to ALL chapter members — social accountability over hard locks."""
    return svc.uncommit_log(
        get_db(),
        chapter_id=user["chapter_id"],
        member_id=member_id,
        limit=limit,
    )


@router.get("/attribution/me")
async def my_attribution(user=Depends(get_current_user)):
    return svc.attribution(
        get_db(), chapter_id=user["chapter_id"], member_id=user["id"]
    )


@router.get("/attribution/{member_id}")
async def member_attribution(member_id: str, user=Depends(get_current_user)):
    """Any member can view any member's ledger (chapter-visible by design)."""
    return svc.attribution(
        get_db(), chapter_id=user["chapter_id"], member_id=member_id
    )


@router.get("/{task_id}/commitments")
async def task_commitments(task_id: str, user=Depends(get_current_user)):
    """Active commitments + full commit/uncommit history for a task."""
    return svc.list_task_commitments(
        get_db(), chapter_id=user["chapter_id"], task_id=task_id
    )
