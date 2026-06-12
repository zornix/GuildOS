"""
Auto-fine generation for required events.

NOTE (GreekOS V1, spec §5 Fines): automatic fines are CUT from V1. The
process-fines Vercel cron entry was removed and /api/cron/process-fines is a
disabled no-op — nothing calls this module on a schedule anymore. It remains
only behind the legacy officer-triggered POST /api/fines/process-event/{event_id}
route. The V1 path is manual: GET /api/fines/missed/{event_id} +
POST /api/fines/issue (flat $25, ≥24h gate, treasury:fines:issue).
"""

from api.db import get_supabase_admin
from api.treasury.api.schemas import FineToInvoice
from api.treasury.db.rpc import call_rpc


async def process_event_fines(event_id: str) -> list[dict]:
    """
    For a required event whose check-in window has closed:
    1. Get all active chapter members
    2. Subtract those who checked in
    3. Subtract those with approved excuses
    4. Issue fines to the rest
    """
    sb = get_supabase_admin()

    event = (
        sb.table("events")
        .select("*")
        .eq("id", event_id)
        .single()
        .execute()
    ).data

    if not event or not event["required"] or event["fine_amount"] <= 0:
        return []

    members = (
        sb.table("members")
        .select("id")
        .eq("chapter_id", event["chapter_id"])
        .eq("status", "active")
        .execute()
    ).data
    all_ids = {m["id"] for m in members}

    checked = (
        sb.table("attendance")
        .select("member_id")
        .eq("event_id", event_id)
        .eq("checked_in", True)
        .execute()
    ).data
    checked_ids = {c["member_id"] for c in checked}

    excused = (
        sb.table("excuses")
        .select("member_id")
        .eq("event_id", event_id)
        .eq("status", "approved")
        .execute()
    ).data
    excused_ids = {e["member_id"] for e in excused}

    # Dedup against fine-kind invoices already created for this event (§7.8: fines
    # are now unpaid_invoices(kind=fine), not rows in the frozen `fines` table).
    already_fined = (
        sb.table("unpaid_invoices")
        .select("member_id")
        .eq("source_event_id", event_id)
        .eq("kind", "fine")
        .execute()
    ).data
    fined_ids = {f["member_id"] for f in already_fined}

    to_fine = all_ids - checked_ids - excused_ids - fined_ids

    # Float→cents boundary: convert the NUMERIC fine_amount exactly once, here.
    fine_amount_cents = FineToInvoice(fine_amount=event["fine_amount"]).fine_amount_cents
    if fine_amount_cents <= 0:
        return []

    new_invoices = []
    for member_id in to_fine:
        # Atomic invoice + ledger + audit via the sanctioned RPC path. No Python
        # recompute here — the auto-fine cron lets the next balance read refresh
        # the cache (Chunk B owns recompute_member).
        result = call_rpc(
            "tr_create_invoice",
            {
                "p_chapter_id": event["chapter_id"],
                "p_member_id": member_id,
                "p_kind": "fine",
                "p_amount_cents": fine_amount_cents,
                "p_description": f"Missed {event['title']} (unexcused)",
                "p_actor_id": None,
                "p_idempotency_key": None,
                "p_source_event_id": event_id,
            },
            sb=sb,
        )
        if result.data:
            new_invoices.append(result.data)

    return new_invoices
