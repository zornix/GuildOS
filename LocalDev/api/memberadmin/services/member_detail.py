"""Per-member event breakdown for MemberAdmin."""

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
        .select("id, title, date, required, fine_amount")
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

    fines = (
        sb.table("fines")
        .select("event_id, amount, status")
        .eq("member_id", member_id)
        .in_("event_id", event_ids)
        .execute()
    ).data
    fine_map = {row["event_id"]: row for row in fines}

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
            "fine_amount": fine["amount"] if fine else None,
            "fine_status": fine["status"] if fine else None,
        })

    return {
        "member": member.data,
        "breakdown": breakdown,
    }
