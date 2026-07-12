"""
Engagement scoring for MemberAdmin.

Score range: 0 (worst) → 100 (perfect).
Lower scores = more delinquent = first pick for security / reminders.
"""

from __future__ import annotations

from api.memberadmin.core.engagement import load_member_engagement


async def compute_engagement_scores(chapter_id: str, *, use_admin: bool = False) -> list[dict]:
    engagements = await load_member_engagement(chapter_id, use_admin=use_admin)

    results = []
    for row in engagements:
        total_required = row.total_required
        attendance_pct = row.attended / total_required if total_required else 1
        excuse_pct = row.excused / total_required if total_required else 0
        fine_penalty = min(row.unpaid_amount_cents / 20000, 0.10)
        score = round((attendance_pct * 70) + (excuse_pct * 20) + ((1 - fine_penalty) * 10), 1)
        score = max(0, min(100, score))

        results.append({
            "member_id": row.member_id,
            "name": row.name,
            "email": row.email,
            "score": score,
            "attended": row.attended,
            "excused": row.excused,
            "missed": row.missed,
            "total_required": total_required,
            "unpaid_fines": row.unpaid_fines,
            "unpaid_amount_cents": row.unpaid_amount_cents,
        })

    results.sort(key=lambda item: item["score"])
    return results
