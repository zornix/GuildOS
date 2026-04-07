from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user, require_officer
from api.models.schemas import ExcuseCreate, ExcuseReview
from api.db import get_supabase

router = APIRouter()


@router.post("/event/{event_id}")
async def submit_excuse(event_id: str, body: ExcuseCreate, user=Depends(get_current_user)):
    """Submit an excuse for missing an event."""
    sb = get_supabase()

    event = (
        sb.table("events")
        .select("id, chapter_id")
        .eq("id", event_id)
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")
    if event.data["chapter_id"] != user["chapter_id"]:
        raise HTTPException(403, "Event does not belong to your chapter")

    existing = (
        sb.table("excuses")
        .select("id, status")
        .eq("event_id", event_id)
        .eq("member_id", user["id"])
        .in_("status", ["pending", "approved"])
        .execute()
    )
    if existing.data:
        raise HTTPException(409, "Excuse already submitted for this event")

    # Delete any previously denied excuse so the new insert succeeds
    # against the unique(event_id, member_id) constraint
    sb.table("excuses") \
        .delete() \
        .eq("event_id", event_id) \
        .eq("member_id", user["id"]) \
        .eq("status", "denied") \
        .execute()

    result = sb.table("excuses").insert({
        "event_id": event_id,
        "member_id": user["id"],
        "reason": body.reason,
        "status": "pending",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    if not result.data:
        raise HTTPException(500, "Failed to submit excuse")

    return result.data[0]


@router.get("/")
async def list_excuses(status: str = None, user=Depends(get_current_user)):
    """
    List excuses.
    Officers: see all for their chapter (filterable by status).
    Members: see only their own.
    """
    sb = get_supabase()

    if user["role"] == "officer":
        query = (
            sb.table("excuses")
            .select("*, members(name, email), events(title, date)")
            .eq("events.chapter_id", user["chapter_id"])
        )
        if status:
            query = query.eq("status", status)
        query = query.order("submitted_at", desc=True)
    else:
        query = (
            sb.table("excuses")
            .select("*, events(title, date)")
            .eq("member_id", user["id"])
            .order("submitted_at", desc=True)
        )

    return query.execute().data


@router.put("/{excuse_id}/review")
async def review_excuse(excuse_id: str, body: ExcuseReview, officer=Depends(require_officer)):
    """Approve or deny an excuse. If approved, remove any associated fine."""
    if body.status not in ("approved", "denied"):
        raise HTTPException(400, "Status must be 'approved' or 'denied'")

    sb = get_supabase()

    excuse = (
        sb.table("excuses")
        .update({
            "status": body.status,
            "reviewed_by": officer["id"],
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", excuse_id)
        .select("*")
        .execute()
    )

    if not excuse.data:
        raise HTTPException(404, "Excuse not found")

    exc = excuse.data[0]

    if body.status == "approved":
        sb.table("fines") \
            .delete() \
            .eq("event_id", exc["event_id"]) \
            .eq("member_id", exc["member_id"]) \
            .eq("status", "unpaid") \
            .execute()

    return exc
