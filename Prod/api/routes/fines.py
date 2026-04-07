from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user, require_officer
from api.services.fine_processor import process_event_fines
from api.db import get_supabase

router = APIRouter()


@router.get("/")
async def list_fines(status: str = None, user=Depends(get_current_user)):
    """List fines. Officers see all chapter fines, members see their own."""
    sb = get_supabase()

    if user["role"] == "officer":
        query = (
            sb.table("fines")
            .select("*, members(name, email), events(title, date)")
            .eq("chapter_id", user["chapter_id"])
        )
    else:
        query = (
            sb.table("fines")
            .select("*, events(title, date)")
            .eq("member_id", user["id"])
        )

    if status:
        query = query.eq("status", status)

    return query.order("issued_at", desc=True).execute().data


@router.post("/{fine_id}/waive")
async def waive_fine(fine_id: str, officer=Depends(require_officer)):
    """Officer waives a fine."""
    sb = get_supabase()
    result = (
        sb.table("fines")
        .update({
            "status": "waived",
            "waived_by": officer["id"],
        })
        .eq("id", fine_id)
        .eq("chapter_id", officer["chapter_id"])
        .eq("status", "unpaid")
        .select("*")
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Fine not found or already resolved")
    return result.data[0]


@router.post("/process-event/{event_id}")
async def process_fines_for_event(event_id: str, officer=Depends(require_officer)):
    """Officer manually triggers fine processing for a specific event."""
    sb = get_supabase()
    event = (
        sb.table("events")
        .select("id, chapter_id, required")
        .eq("id", event_id)
        .eq("chapter_id", officer["chapter_id"])
        .single()
        .execute()
    )
    if not event.data:
        raise HTTPException(404, "Event not found")
    if not event.data["required"]:
        raise HTTPException(400, "Event is not required — no fines to process")

    fines = await process_event_fines(event_id)
    return {"event_id": event_id, "fines_issued": len(fines)}


@router.get("/summary")
async def fine_summary(officer=Depends(require_officer)):
    """Aggregate fine stats for the chapter."""
    sb = get_supabase()
    fines = (
        sb.table("fines")
        .select("amount, status")
        .eq("chapter_id", officer["chapter_id"])
        .execute()
    ).data

    summary = {"total_unpaid": 0, "total_paid": 0, "total_waived": 0, "count_unpaid": 0}
    for f in fines:
        if f["status"] == "unpaid":
            summary["total_unpaid"] += f["amount"]
            summary["count_unpaid"] += 1
        elif f["status"] == "paid":
            summary["total_paid"] += f["amount"]
        elif f["status"] == "waived":
            summary["total_waived"] += f["amount"]

    return summary
