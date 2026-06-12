"""Fines route (Chunk A).

The legacy `fines` table is frozen (§7.8). Fines are now unpaid_invoices(kind=fine):
- listing/summary read fine-kind invoices,
- a waive maps to an invoice cancel (unpaid-only),
- processing an event creates fine invoices via the Treasury RPC path.
"""

from fastapi import APIRouter, Depends, HTTPException

from api.db import get_supabase
from api.dependencies import get_current_user, require_officer
from api.treasury.services.fine_processor import process_event_fines
from api.treasury.db.session import get_treasury_db
from api.treasury.services import invoices as invoice_svc

router = APIRouter()


@router.get("/")
async def list_fines(status: str = None, user=Depends(get_current_user)):
    """List fine invoices. Officers see all chapter fines; members see their own."""
    sb = get_supabase()

    query = sb.table("unpaid_invoices").select("*").eq("kind", "fine")
    if user["role"] == "officer":
        query = query.eq("chapter_id", user["chapter_id"])
    else:
        query = query.eq("member_id", user["id"])
    if status:
        query = query.eq("status", status)

    return query.order("created_at", desc=True).execute().data


@router.post("/{invoice_id}/waive")
async def waive_fine(invoice_id: str, officer=Depends(require_officer)):
    """Officer waives a fine — i.e. cancels the underlying unpaid invoice."""
    sb = get_treasury_db()
    try:
        return invoice_svc.cancel_invoice(
            sb,
            chapter_id=officer["chapter_id"],
            invoice_id=invoice_id,
            actor_id=officer["id"],
        )
    except Exception as exc:  # invoice not found / not unpaid
        raise HTTPException(404, f"Fine not found or not waivable: {exc}")


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

    invoices = await process_event_fines(event_id)
    return {"event_id": event_id, "fines_issued": len(invoices)}


@router.get("/summary")
async def fine_summary(officer=Depends(require_officer)):
    """Aggregate fine stats for the chapter, in cents."""
    sb = get_supabase()
    invoices = (
        sb.table("unpaid_invoices")
        .select("amount_cents, status")
        .eq("chapter_id", officer["chapter_id"])
        .eq("kind", "fine")
        .execute()
    ).data

    summary = {"total_unpaid_cents": 0, "total_paid_cents": 0, "total_cancelled_cents": 0, "count_unpaid": 0}
    for inv in invoices:
        amt = inv["amount_cents"]
        if inv["status"] in ("unpaid", "partially_paid"):
            summary["total_unpaid_cents"] += amt
            summary["count_unpaid"] += 1
        elif inv["status"] == "paid":
            summary["total_paid_cents"] += amt
        elif inv["status"] == "cancelled":
            summary["total_cancelled_cents"] += amt

    return summary
