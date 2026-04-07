from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user, require_officer
from api.models.schemas import EventCreate, EventUpdate, CheckInLinkResponse
from api.services.checkin_links import create_checkin_link, deactivate_checkin_link
from api.db import get_supabase

router = APIRouter()


@router.get("/")
async def list_events(upcoming: bool = True, user=Depends(get_current_user)):
    """List events for the user's chapter."""
    sb = get_supabase()
    query = (
        sb.table("events")
        .select("*")
        .eq("chapter_id", user["chapter_id"])
        .order("date", desc=not upcoming)
    )
    result = query.execute()
    return result.data


@router.post("/")
async def create_event(body: EventCreate, officer=Depends(require_officer)):
    """Create a new event."""
    sb = get_supabase()
    result = sb.table("events").insert({
        "chapter_id": officer["chapter_id"],
        "title": body.title,
        "description": body.description,
        "date": body.date.isoformat(),
        "time": body.time.isoformat(),
        "location": body.location,
        "required": body.required,
        "fine_amount": body.fine_amount,
        "created_by": officer["id"],
    }).execute()
    return result.data[0]


@router.get("/{event_id}")
async def get_event(event_id: str, user=Depends(get_current_user)):
    """Get event details with attendance summary."""
    sb = get_supabase()
    event = (
        sb.table("events")
        .select("*")
        .eq("id", event_id)
        .eq("chapter_id", user["chapter_id"])
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")

    att = (
        sb.table("attendance")
        .select("id", count="exact")
        .eq("event_id", event_id)
        .eq("checked_in", True)
        .execute()
    )
    event.data["attendance_count"] = att.count
    return event.data


@router.put("/{event_id}")
async def update_event(event_id: str, body: EventUpdate, officer=Depends(require_officer)):
    """Update an event."""
    sb = get_supabase()
    updates = body.model_dump(exclude_none=True)
    if "date" in updates:
        updates["date"] = updates["date"].isoformat()
    if "time" in updates:
        updates["time"] = updates["time"].isoformat()

    result = (
        sb.table("events")
        .update(updates)
        .eq("id", event_id)
        .eq("chapter_id", officer["chapter_id"])
        .execute()
    )
    return result.data[0] if result.data else None


@router.delete("/{event_id}")
async def delete_event(event_id: str, officer=Depends(require_officer)):
    """Delete an event."""
    sb = get_supabase()
    sb.table("events") \
        .delete() \
        .eq("id", event_id) \
        .eq("chapter_id", officer["chapter_id"]) \
        .execute()
    return {"deleted": True}


@router.post("/{event_id}/checkin-link", response_model=CheckInLinkResponse)
async def generate_checkin_link(event_id: str, officer=Depends(require_officer)):
    """
    Generate a short-lived check-in link for an event.
    Officer shows this link (or its QR) to members in-person.
    Any previous active link for this event is deactivated.
    """
    sb = get_supabase()
    event = (
        sb.table("events")
        .select("id")
        .eq("id", event_id)
        .eq("chapter_id", officer["chapter_id"])
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")

    link = await create_checkin_link(event_id, officer["id"])
    return link


@router.delete("/{event_id}/checkin-link")
async def kill_checkin_link(event_id: str, officer=Depends(require_officer)):
    """Manually deactivate the current check-in link."""
    await deactivate_checkin_link(event_id)
    return {"deactivated": True}
