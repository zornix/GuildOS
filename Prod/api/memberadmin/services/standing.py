"""Member standing buckets derived from shared engagement aggregates.

Statuses + reason codes come from core.standing_rules (pure). Standing reads
fines + unexcused absences and nothing else: per ADR-0004 this module must not
import the tasks/contribution seam, so there is no task-count lookup here.
"""

from __future__ import annotations

from api.memberadmin.core.engagement import load_member_engagement
from api.memberadmin.core.standing_rules import derive_standing


async def compute_member_standings(chapter_id: str) -> list[dict]:
    engagements = await load_member_engagement(chapter_id, include_role=True)

    results = []
    for row in engagements:
        status, reason_codes = derive_standing(
            unpaid_count=row.unpaid_fines,
            unpaid_total_cents=row.unpaid_amount_cents,
            unexcused=row.missed,
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
