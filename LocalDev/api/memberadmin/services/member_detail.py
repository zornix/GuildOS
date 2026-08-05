"""Per-member event breakdown for MemberAdmin.

Money in the breakdown is integer cents (`fine_amount_cents`), sourced from the
treasury receivable (`unpaid_invoices`, kind='fine') the events→invoices import
writes — never from the frozen legacy `fines` table.
"""

from __future__ import annotations

from fastapi import HTTPException

from api.db import get_supabase


async def load_member_event_breakdown(chapter_id: str, member_id: str) -> dict:
    sb = get_supabase()

    member = (
        sb.table("members")
        .select("id, name, email")
        .eq("id", member_id)
        .eq("chapter_id", chapter_id)
        .single()
        .execute()
    )
    if not member.data:
        raise HTTPException(404, "Member not found")

    events = (
        sb.table("events")
        .select("id, title, date, required")
        .eq("chapter_id", chapter_id)
        .eq("required", True)
        .order("date", desc=True)
        .execute()
    ).data

    event_ids = [event["id"] for event in events]

    attendance = (
        sb.table("attendance")
        .select("event_id, checked_in, checked_in_at, method")
        .eq("member_id", member_id)
        .in_("event_id", event_ids)
        .execute()
    ).data
    att_map = {row["event_id"]: row for row in attendance}

    excuses = (
        sb.table("excuses")
        .select("event_id, status, reason, submitted_at")
        .eq("member_id", member_id)
        .in_("event_id", event_ids)
        .execute()
    ).data
    exc_map = {row["event_id"]: row for row in excuses}

    # V1 fines are treasury invoices (`unpaid_invoices`, kind='fine', integer
    # cents), not the legacy `fines` table — frozen since 0012 and always empty,
    # so reading it reported every fine as null. Same source as
    # memberadmin.core.engagement, chapter-scoped like the reads above.
    fines = (
        sb.table("unpaid_invoices")
        .select("source_event_id, amount_cents, status")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .eq("kind", "fine")
        .in_("source_event_id", event_ids)
        .execute()
    ).data or []
    # A voided invoice is not a fine the member owes or ever paid.
    fine_map = {
        row["source_event_id"]: row for row in fines if row["status"] != "cancelled"
    }

    breakdown = []
    for event in events:
        event_id = event["id"]
        att = att_map.get(event_id)
        exc = exc_map.get(event_id)
        fine = fine_map.get(event_id)

        if att and att["checked_in"]:
            status = "present"
        elif exc and exc["status"] == "approved":
            status = "excused"
        elif exc and exc["status"] == "pending":
            status = "excuse_pending"
        else:
            status = "absent"

        breakdown.append({
            "event_id": event_id,
            "event_title": event["title"],
            "event_date": event["date"],
            "status": status,
            # Integer cents (hard rule); renamed from the dollars-shaped
            # `fine_amount` because the old key only ever emitted null.
            "fine_amount_cents": fine["amount_cents"] if fine else None,
            "fine_status": fine["status"] if fine else None,
        })

    return {
        "member": member.data,
        "breakdown": breakdown,
    }
