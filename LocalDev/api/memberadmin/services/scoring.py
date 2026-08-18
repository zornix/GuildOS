"""
Engagement scoring for MemberAdmin.

Score range: 0 (worst) → 100 (perfect).
Lower scores = more delinquent = first pick for security / reminders.
"""

from __future__ import annotations

from api.memberadmin.core.engagement import load_member_engagement
from api.platform.db import get_db


def _prior_security_shifts(chapter_id: str) -> dict[str, int]:
    """How many approved security jobs each member has held (D17).

    Decoration only — the security picker's "prior shifts" column (spec Screen
    6). Never an input to the 0–100 score, and never shown on the assigned
    member's card. The active commitment is the source of truth for the holder
    (D12); an approved job's commitment may be 'active' or 'completed', so both
    count.
    """
    sb = get_db()
    task_ids = [
        str(r["id"])
        for r in (
            sb.table("tasks")
            .select("id")
            .eq("chapter_id", chapter_id)
            .eq("kind", "security")
            .eq("status", "approved")
            .execute()
        ).data
        or []
    ]
    if not task_ids:
        return {}

    tally: dict[str, int] = {}
    for row in (
        sb.table("task_commitments")
        .select("member_id, status")
        .in_("task_id", task_ids)
        .in_("status", ["active", "completed"])
        .execute()
    ).data or []:
        member_id = str(row["member_id"])
        tally[member_id] = tally.get(member_id, 0) + 1
    return tally


async def compute_engagement_scores(chapter_id: str) -> list[dict]:
    engagements = await load_member_engagement(chapter_id)
    prior_shifts = _prior_security_shifts(chapter_id)

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
            "prior_security_shifts": prior_shifts.get(str(row.member_id), 0),
        })

    results.sort(key=lambda item: item["score"])
    return results
