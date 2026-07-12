"""Member standing buckets derived from shared engagement aggregates.

Statuses + reason codes come from core.standing_rules (pure); the tasks signal
is read from the tasks service seam (§7) and currently contributes reason codes
only — see the TODO in standing_rules.
"""

from __future__ import annotations

from api.memberadmin.core.engagement import load_member_engagement
from api.memberadmin.core.standing_rules import derive_standing


def _incomplete_required_tasks_by_member(chapter_id: str) -> dict[str, int]:
    from api.tasks.db.session import get_tasks_db
    from api.tasks.services.tasks import incomplete_required_tasks

    counts: dict[str, int] = {}
    for task in incomplete_required_tasks(get_tasks_db(), chapter_id=chapter_id):
        mid = task.get("assigned_member_id")
        if mid:
            counts[mid] = counts.get(mid, 0) + 1
    return counts


async def compute_member_standings(chapter_id: str) -> list[dict]:
    engagements = await load_member_engagement(chapter_id, include_role=True)
    task_counts = _incomplete_required_tasks_by_member(chapter_id)

    results = []
    for row in engagements:
        status, reason_codes = derive_standing(
            unpaid_count=row.unpaid_fines,
            unpaid_total_cents=row.unpaid_amount_cents,
            unexcused=row.missed,
            incomplete_required_tasks=task_counts.get(row.member_id, 0),
        )
        results.append({
            "member_id": row.member_id,
            "name": row.name,
            "email": row.email,
            "standing": status,
            "reason_codes": reason_codes,
            "attended": row.attended,
            "total_required": row.total_required,
            "unexcused_absences": row.missed,
            "unpaid_fines": row.unpaid_fines,
            "unpaid_amount_cents": row.unpaid_amount_cents,
        })

    order = {"delinquent": 0, "warning": 1, "good_standing": 2}
    results.sort(key=lambda item: order[item["standing"]])
    return results
