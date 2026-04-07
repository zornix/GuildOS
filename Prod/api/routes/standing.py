from fastapi import APIRouter, Depends

from api.dependencies import get_current_user, require_officer
from api.db import get_supabase

router = APIRouter()


@router.get("/")
async def get_standings(officer=Depends(require_officer)):
    """
    Simple member standing based on explicit rules:
      - good_standing: no issues
      - warning: 1 unpaid fine OR 1+ unexcused absence
      - delinquent: 2+ unpaid fines OR $50+ unpaid OR 3+ unexcused absences
    """
    sb = get_supabase()
    chapter_id = officer["chapter_id"]

    members = (
        sb.table("members")
        .select("id, name, email, role")
        .eq("chapter_id", chapter_id)
        .eq("status", "active")
        .order("name")
        .execute()
    ).data

    required_events = (
        sb.table("events")
        .select("id")
        .eq("chapter_id", chapter_id)
        .eq("required", True)
        .lte("date", "now()")
        .execute()
    ).data
    event_ids = [e["id"] for e in required_events]
    total_required = len(event_ids)

    if not event_ids:
        return [
            {
                "member_id": m["id"],
                "name": m["name"],
                "email": m["email"],
                "standing": "good_standing",
                "attended": 0,
                "total_required": 0,
                "unexcused_absences": 0,
                "unpaid_fines": 0,
                "unpaid_amount": 0.0,
            }
            for m in members
        ]

    attendance = (
        sb.table("attendance")
        .select("member_id, event_id")
        .in_("event_id", event_ids)
        .eq("checked_in", True)
        .execute()
    ).data
    att_by_member: dict[str, set[str]] = {}
    for a in attendance:
        att_by_member.setdefault(a["member_id"], set()).add(a["event_id"])

    excuses = (
        sb.table("excuses")
        .select("member_id, event_id")
        .in_("event_id", event_ids)
        .eq("status", "approved")
        .execute()
    ).data
    exc_by_member: dict[str, set[str]] = {}
    for e in excuses:
        exc_by_member.setdefault(e["member_id"], set()).add(e["event_id"])

    fines = (
        sb.table("fines")
        .select("member_id, amount")
        .eq("chapter_id", chapter_id)
        .eq("status", "unpaid")
        .execute()
    ).data
    fines_by_member: dict[str, list[dict]] = {}
    for f in fines:
        fines_by_member.setdefault(f["member_id"], []).append(f)

    results = []
    for m in members:
        mid = m["id"]
        attended = att_by_member.get(mid, set())
        excused = exc_by_member.get(mid, set()) - attended
        unexcused = max(total_required - len(attended) - len(excused), 0)
        member_fines = fines_by_member.get(mid, [])
        unpaid_count = len(member_fines)
        unpaid_total = sum(f["amount"] for f in member_fines)

        if unpaid_count >= 2 or unpaid_total >= 50 or unexcused >= 3:
            standing = "delinquent"
        elif unpaid_count >= 1 or unexcused >= 1:
            standing = "warning"
        else:
            standing = "good_standing"

        results.append({
            "member_id": mid,
            "name": m["name"],
            "email": m["email"],
            "standing": standing,
            "attended": len(attended),
            "total_required": total_required,
            "unexcused_absences": unexcused,
            "unpaid_fines": unpaid_count,
            "unpaid_amount": unpaid_total,
        })

    order = {"delinquent": 0, "warning": 1, "good_standing": 2}
    results.sort(key=lambda r: order[r["standing"]])
    return results
