"""
Delinquency scoring engine.

Computes an engagement score per active member based on:
  - Attendance at required events (heaviest weight)
  - Approved excuses (partial credit)
  - Unpaid fines (penalty)

Score range: 0 (worst) → 100 (perfect).
Lower scores = more delinquent = first pick for security / reminders.
"""

from api.db import get_supabase, get_supabase_admin


async def compute_delinquency_scores(chapter_id: str, *, use_admin: bool = False) -> list[dict]:
    sb = get_supabase_admin() if use_admin else get_supabase()

    members = (
        sb.table("members")
        .select("id, name, email")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .execute()
    ).data

    required_events = (
        sb.table("events")
        .select("id, title, date, fine_amount")
        .eq("chapter_id", chapter_id)
        .eq("required", True)
        .lte("date", "now()")
        .execute()
    ).data

    if not required_events:
        return [
            {
                "member_id": m["id"],
                "name": m["name"],
                "email": m["email"],
                "score": 100,
                "attended": 0,
                "excused": 0,
                "missed": 0,
                "total_required": 0,
                "unpaid_fines": 0,
                "unpaid_amount": 0.0,
            }
            for m in members
        ]

    event_ids = [e["id"] for e in required_events]
    total_required = len(event_ids)

    attendance = (
        sb.table("attendance")
        .select("member_id, event_id, checked_in")
        .in_("event_id", event_ids)
        .eq("checked_in", True)
        .execute()
    ).data

    excuses = (
        sb.table("excuses")
        .select("member_id, event_id, status")
        .in_("event_id", event_ids)
        .eq("status", "approved")
        .execute()
    ).data

    fines = (
        sb.table("fines")
        .select("member_id, amount, status")
        .eq("chapter_id", chapter_id)
        .eq("status", "unpaid")
        .execute()
    ).data

    att_by_member: dict[str, set[str]] = {}
    for a in attendance:
        att_by_member.setdefault(a["member_id"], set()).add(a["event_id"])

    exc_by_member: dict[str, set[str]] = {}
    for e in excuses:
        exc_by_member.setdefault(e["member_id"], set()).add(e["event_id"])

    fines_by_member: dict[str, list[dict]] = {}
    for f in fines:
        fines_by_member.setdefault(f["member_id"], []).append(f)

    results = []
    for m in members:
        mid = m["id"]
        attended = att_by_member.get(mid, set())
        excused = exc_by_member.get(mid, set()) - attended
        missed = total_required - len(attended) - len(excused)
        member_fines = fines_by_member.get(mid, [])
        unpaid_amount = sum(f["amount"] for f in member_fines)

        attendance_pct = len(attended) / total_required if total_required else 1
        excuse_pct = len(excused) / total_required if total_required else 0
        # Attendance = 70%, excused = 20% credit, fines penalty up to 10%
        fine_penalty = min(unpaid_amount / 200, 0.10)
        score = round((attendance_pct * 70) + (excuse_pct * 20) + ((1 - fine_penalty) * 10), 1)
        score = max(0, min(100, score))

        results.append({
            "member_id": mid,
            "name": m["name"],
            "email": m["email"],
            "score": score,
            "attended": len(attended),
            "excused": len(excused),
            "missed": max(missed, 0),
            "total_required": total_required,
            "unpaid_fines": len(member_fines),
            "unpaid_amount": unpaid_amount,
        })

    results.sort(key=lambda r: r["score"])
    return results
