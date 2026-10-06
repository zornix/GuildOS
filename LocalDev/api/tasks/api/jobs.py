"""Job lifecycle HTTP surface — report-done / approve / reject.

Mounted under `/api/tasks` by router.py. Report-done is a claimant action
(claimant-checked in the RPC); approve/reject are approver actions gated by
can_approve_job (403 otherwise). RPC guard violations map to client errors.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import get_current_user
from api.tasks.api.schemas import RejectIn
from api.tasks.auth import TASKS_COMPLETE
from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.tasks.services import jobs as svc
from api.tasks.services.approvals import can_approve_job
from api.tasks.services.tasks import get_task

router = APIRouter()

import logging

logger = logging.getLogger(__name__)


# State/uniqueness conflicts every tk_* route maps to 409. Shared with tasks.py
# (PATCH/DELETE) so the mapping lives in one place.
_CONFLICT = (
    "already_reported",
    "job_full",
    "unclaim_locked",
    "security_preassigned",
    "security_no_unclaim",
    "security_no_edit",
    "security_no_cancel",
    "job_not_editable",
    "job_not_cancellable",
    "job_capacity_below_claims",
    "cannot be reported",
    "cannot be approved",
    "cannot be rejected",
)


def _rpc_http_error(exc: Exception) -> HTTPException:
    """Map tk_* job-lifecycle RPC exceptions onto HTTP statuses."""
    msg = str(exc)
    if "not found" in msg:
        return HTTPException(404, "Task not found")
    if "rejection_reason_required" in msg:
        return HTTPException(422, "A rejection reason is required")
    if "job_title_required" in msg:
        return HTTPException(422, "A job title is required")
    if "job_people_needed_invalid" in msg:
        return HTTPException(422, "Job capacity must be at least one")
    if "security_no_status_change" in msg:
        return HTTPException(400, "security_no_status_change")
    if "no active commitment" in msg:
        return HTTPException(403, "Only a claimant of this job can report it done")
    for token in _CONFLICT:
        if token in msg:
            detail = {
                "cannot be reported": "Job cannot be reported done",
                "cannot be approved": "Job cannot be approved",
                "cannot be rejected": "Job cannot be rejected",
            }.get(token, token)
            return HTTPException(409, detail)
    # Unmapped: log here because returning (not raising the original) skips
    # the observability catch-all that would have recorded the trace.
    logger.exception("unmapped RPC error")
    return HTTPException(500, "Internal server error")


def _load_task_or_404(sb, *, chapter_id: str, task_id: str) -> dict:
    task = get_task(sb, chapter_id=chapter_id, task_id=task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.post("/{task_id}/report-done")
async def report_done(
    task_id: str,
    user=Depends(require_permission(TASKS_COMPLETE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """A claimant reports their job done (🟢 → 🟡). Claimant is enforced in the RPC."""
    sb = get_db()
    try:
        return svc.report_done(
            sb,
            chapter_id=user["chapter_id"],
            task_id=task_id,
            member_id=user["id"],
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise _rpc_http_error(exc) from exc


@router.post("/{task_id}/approve")
async def approve_task(
    task_id: str,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Approve a reported job (🟡 → ✅). Approver must run the linked event
    (supervisor) or hold tasks:review for standalone jobs."""
    sb = get_db()
    task = _load_task_or_404(sb, chapter_id=user["chapter_id"], task_id=task_id)
    if not can_approve_job(sb, user=user, task=task):
        raise HTTPException(403, "You are not authorized to approve this job")
    try:
        return svc.approve_task(
            sb,
            chapter_id=user["chapter_id"],
            task_id=task_id,
            actor_id=user["id"],
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise _rpc_http_error(exc) from exc


@router.post("/{task_id}/reject")
async def reject_task(
    task_id: str,
    body: RejectIn,
    user=Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Reject a reported job with a required reason (🟡 → 🟢/🔴)."""
    sb = get_db()
    task = _load_task_or_404(sb, chapter_id=user["chapter_id"], task_id=task_id)
    if not can_approve_job(sb, user=user, task=task):
        raise HTTPException(403, "You are not authorized to reject this job")
    try:
        return svc.reject_task(
            sb,
            chapter_id=user["chapter_id"],
            task_id=task_id,
            actor_id=user["id"],
            reason=body.reason,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        raise _rpc_http_error(exc) from exc
