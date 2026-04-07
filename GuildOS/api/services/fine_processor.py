"""
Auto-fine generation for required events.

Runs after check-in window closes. Deploy as: Supabase Edge Function
with pg_cron, or Vercel Cron.

vercel.json cron config:
{
  "crons": [{
    "path": "/api/cron/process-fines",
    "schedule": "*/15 * * * *"
  }]
}
"""

from datetime import datetime, timezone

from api.db import get_supabase_admin


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

    already_fined = (
        sb.table("fines")
        .select("member_id")
        .eq("event_id", event_id)
        .execute()
    ).data
    fined_ids = {f["member_id"] for f in already_fined}

    to_fine = all_ids - checked_ids - excused_ids - fined_ids

    new_fines = []
    for member_id in to_fine:
        result = sb.table("fines").insert({
            "event_id": event_id,
            "member_id": member_id,
            "chapter_id": event["chapter_id"],
            "amount": event["fine_amount"],
            "reason": f"Missed {event['title']} (unexcused)",
            "status": "unpaid",
            "issued_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        if result.data:
            new_fines.append(result.data[0])

    return new_fines
