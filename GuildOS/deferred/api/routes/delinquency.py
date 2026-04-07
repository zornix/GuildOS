from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user, require_officer
from api.services.delinquency import compute_delinquency_scores
from api.db import get_supabase

router = APIRouter()


@router.get("/scores")
async def get_delinquency_scores(officer=Depends(require_officer)):
    """Ranked member engagement scores — lowest (most delinquent) first."""
    return await compute_delinquency_scores(officer["chapter_id"])


@router.get("/member/{member_id}")
async def get_member_detail(member_id: str, officer=Depends(require_officer)):
    """Per-event breakdown for a single member."""
    sb = get_supabase()

    member = (
        sb.table("members")
        .select("id, name, email")
        .eq("id", member_id)
        .eq("chapter_id", officer["chapter_id"])
        .single()
        .execute()
    )
    if not member.data:
        raise HTTPException(404, "Member not found")

    events = (
        sb.table("events")
        .select("id, title, date, required, fine_amount")
        .eq("chapter_id", officer["chapter_id"])
        .eq("required", True)
        .order("date", desc=True)
        .execute()
    ).data

    event_ids = [e["id"] for e in events]

    attendance = (
        sb.table("attendance")
        .select("event_id, checked_in, checked_in_at, method")
        .eq("member_id", member_id)
        .in_("event_id", event_ids)
        .execute()
    ).data
    att_map = {a["event_id"]: a for a in attendance}

    excuses = (
        sb.table("excuses")
        .select("event_id, status, reason, submitted_at")
        .eq("member_id", member_id)
        .in_("event_id", event_ids)
        .execute()
    ).data
    exc_map = {e["event_id"]: e for e in excuses}

    fines = (
        sb.table("fines")
        .select("event_id, amount, status")
        .eq("member_id", member_id)
        .in_("event_id", event_ids)
        .execute()
    ).data
    fine_map = {f["event_id"]: f for f in fines}

    breakdown = []
    for ev in events:
        eid = ev["id"]
        att = att_map.get(eid)
        exc = exc_map.get(eid)
        fine = fine_map.get(eid)

        if att and att["checked_in"]:
            status = "present"
        elif exc and exc["status"] == "approved":
            status = "excused"
        elif exc and exc["status"] == "pending":
            status = "excuse_pending"
        else:
            status = "absent"

        breakdown.append({
            "event_id": eid,
            "event_title": ev["title"],
            "event_date": ev["date"],
            "status": status,
            "fine_amount": fine["amount"] if fine else None,
            "fine_status": fine["status"] if fine else None,
        })

    return {
        "member": member.data,
        "breakdown": breakdown,
    }


@router.post("/assign-security")
async def assign_security(officer=Depends(require_officer)):
    """
    Auto-select the most delinquent members for party security.
    Returns the bottom-ranked members (configurable count, default 3).
    """
    scores = await compute_delinquency_scores(officer["chapter_id"])
    count = min(3, len(scores))
    picks = scores[:count]
    return {
        "assigned": [
            {"member_id": p["member_id"], "name": p["name"], "score": p["score"]}
            for p in picks
        ],
    }


@router.post("/remind/{member_id}")
async def send_reminder(member_id: str, officer=Depends(require_officer)):
    """
    Placeholder: send a payment / engagement reminder to a member.
    In production, hook into email or push notifications.
    """
    sb = get_supabase()
    member = (
        sb.table("members")
        .select("id, name, email")
        .eq("id", member_id)
        .eq("chapter_id", officer["chapter_id"])
        .single()
        .execute()
    )
    if not member.data:
        raise HTTPException(404, "Member not found")

    unpaid = (
        sb.table("fines")
        .select("id, amount")
        .eq("member_id", member_id)
        .eq("status", "unpaid")
        .execute()
    ).data

    # TODO: integrate email/push notification service
    return {
        "sent_to": member.data["email"],
        "name": member.data["name"],
        "unpaid_count": len(unpaid),
        "unpaid_total": sum(f["amount"] for f in unpaid),
        "message": "Reminder queued",
    }
