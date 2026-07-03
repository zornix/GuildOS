"""Job approval authorization (spec §2.4).

Who may approve/reject a reported job:
  - event-linked jobs: any supervisor of the linked event;
  - standalone jobs: holders of tasks:review.

Who may create a job attached to an event (spec §5):
  - a supervisor or organizer of that event, or a holder of tasks:assign.

-- PHASE3 SEAM: initiative chairs plug into can_approve_job for initiative jobs.
"""

from __future__ import annotations

from api.rbac.services.permissions import has_permission
from api.tasks.auth import TASKS_ASSIGN, TASKS_REVIEW


def _is_event_supervisor(sb, *, event_id: str, member_id: str) -> bool:
    return bool(
        (
            sb.table("event_supervisors")
            .select("id")
            .eq("event_id", event_id)
            .eq("member_id", member_id)
            .execute()
        ).data
    )


def _is_event_organizer(sb, *, event_id: str, member_id: str) -> bool:
    return bool(
        (
            sb.table("event_organizers")
            .select("id")
            .eq("event_id", event_id)
            .eq("member_id", member_id)
            .execute()
        ).data
    )


def can_approve_job(sb, *, user: dict, task: dict) -> bool:
    """True when `user` may approve/reject the given job (reported → ✅ / 🔴)."""
    event_id = task.get("event_id")
    if event_id:
        return _is_event_supervisor(sb, event_id=event_id, member_id=user["id"])
    return has_permission(user, TASKS_REVIEW, sb=sb)


def can_create_event_job(sb, *, user: dict, event_id: str) -> bool:
    """True when `user` may attach a new job to `event_id` (spec §5)."""
    if _is_event_supervisor(sb, event_id=event_id, member_id=user["id"]):
        return True
    if _is_event_organizer(sb, event_id=event_id, member_id=user["id"]):
        return True
    return has_permission(user, TASKS_ASSIGN, sb=sb)
