"""Member standing buckets derived from shared engagement aggregates."""

from __future__ import annotations

from api.memberadmin.core.engagement import load_member_engagement


def _classify_standing(unpaid_count: int, unpaid_total: float, unexcused: int) -> str:
    if unpaid_count >= 2 or unpaid_total >= 50 or unexcused >= 3:
        return "delinquent"
    if unpaid_count >= 1 or unexcused >= 1:
        return "warning"
    return "good_standing"


async def compute_member_standings(chapter_id: str) -> list[dict]:
    engagements = await load_member_engagement(chapter_id, include_role=True)

    results = []
    for row in engagements:
        results.append({
            "member_id": row.member_id,
            "name": row.name,
            "email": row.email,
            "standing": _classify_standing(row.unpaid_fines, row.unpaid_amount, row.missed),
            "attended": row.attended,
            "total_required": row.total_required,
            "unexcused_absences": row.missed,
            "unpaid_fines": row.unpaid_fines,
            "unpaid_amount": row.unpaid_amount,
        })

    order = {"delinquent": 0, "warning": 1, "good_standing": 2}
    results.sort(key=lambda item: order[item["standing"]])
    return results
