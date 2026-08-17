"""Job lifecycle service — report-done / approve / reject via tk_* RPCs.

Storage/RPCs stay tasks/tk_* (decision D1). The state machine + tenancy +
outbox fan-out live in the RPCs (0142); approver authorization is decided in
api/tasks/services/approvals.py and enforced by the routes.
"""

from __future__ import annotations

from api.platform.rpc import call_rpc


def report_done(
    sb,
    *,
    chapter_id: str,
    task_id: str,
    member_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tk_report_done",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_member_id": member_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def approve_task(
    sb,
    *,
    chapter_id: str,
    task_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tk_approve_task",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def reject_task(
    sb,
    *,
    chapter_id: str,
    task_id: str,
    actor_id: str,
    reason: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tk_reject_task",
        {
            "p_chapter_id": chapter_id,
            "p_task_id": task_id,
            "p_actor_id": actor_id,
            "p_reason": reason,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data
