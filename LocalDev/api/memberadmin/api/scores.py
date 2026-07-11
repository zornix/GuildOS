from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_officer
from api.db import get_supabase
from api.memberadmin.services.member_detail import load_member_event_breakdown
from api.memberadmin.services.scoring import compute_engagement_scores

router = APIRouter()


@router.get("/scores")
async def get_engagement_scores(officer=Depends(require_officer)):
    """Ranked member engagement scores — lowest (most delinquent) first."""
    return await compute_engagement_scores(officer["chapter_id"])


@router.get("/member/{member_id}")
async def get_member_detail(member_id: str, officer=Depends(require_officer)):
    """Per-event breakdown for a single member."""
    return await load_member_event_breakdown(officer["chapter_id"], member_id)


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

    return {
        "sent_to": member.data["email"],
        "name": member.data["name"],
        "unpaid_count": len(unpaid),
        "unpaid_total": sum(fine["amount"] for fine in unpaid),
        "message": "Reminder queued",
    }
