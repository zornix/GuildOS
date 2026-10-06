"""Job approval authorization.

Who may approve/reject a reported job:
  - event-linked jobs: any supervisor of the linked event;
  - initiative-linked jobs: any chair of the linked initiative;
  - standalone jobs: holders of tasks:review.

Who may create a job attached to an event:
  - a supervisor or organizer of that event, or a holder of tasks:assign.

Who may create a job attached to an initiative:
  - an assigned chair of that initiative, or a holder of tasks:assign.

Who may edit/cancel an existing job: whoever may attach one to
its parent; standalone jobs fall back to tasks:assign or tasks:review.
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


def _is_initiative_chair(sb, *, initiative_id: str, member_id: str) -> bool:
    return bool(
        (
            sb.table("initiative_chairs")
            .select("id")
            .eq("initiative_id", initiative_id)
            .eq("member_id", member_id)
            .execute()
        ).data
    )


def can_approve_job(sb, *, user: dict, task: dict) -> bool:
    """True when `user` may approve/reject the given job (reported → ✅ / 🔴)."""
    event_id = task.get("event_id")
    if event_id:
        return _is_event_supervisor(sb, event_id=event_id, member_id=user["id"])
    initiative_id = task.get("initiative_id")
    if initiative_id:
        return _is_initiative_chair(
            sb, initiative_id=initiative_id, member_id=user["id"]
        )
    return has_permission(user, TASKS_REVIEW, sb=sb)


def can_create_event_job(sb, *, user: dict, event_id: str) -> bool:
    """True when `user` may attach a new job to `event_id`."""
    if _is_event_supervisor(sb, event_id=event_id, member_id=user["id"]):
        return True
    if _is_event_organizer(sb, event_id=event_id, member_id=user["id"]):
        return True
    return has_permission(user, TASKS_ASSIGN, sb=sb)


def can_create_initiative_job(sb, *, user: dict, initiative_id: str) -> bool:
    """True when `user` may attach a new job to `initiative_id`."""
    if _is_initiative_chair(sb, initiative_id=initiative_id, member_id=user["id"]):
        return True
    return has_permission(user, TASKS_ASSIGN, sb=sb)


def can_manage_job(sb, *, user: dict, task: dict) -> bool:
    """True when `user` may edit or cancel an existing job.

    Same people who may attach the job to its parent may maintain it; a
    standalone job has no parent to run, so it falls back to the assign/review
    permissions.
    """
    event_id = task.get("event_id")
    if event_id:
        return can_create_event_job(sb, user=user, event_id=event_id)
    initiative_id = task.get("initiative_id")
    if initiative_id:
        return can_create_initiative_job(sb, user=user, initiative_id=initiative_id)
    return has_permission(user, TASKS_ASSIGN, sb=sb) or has_permission(
        user, TASKS_REVIEW, sb=sb
    )
