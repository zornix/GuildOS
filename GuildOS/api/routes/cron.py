from datetime import datetime, timezone

from fastapi import APIRouter, Header

from api.db import get_supabase_admin
from api.services.fine_processor import process_event_fines

router = APIRouter()


@router.get("/process-fines")
async def cron_process_fines(authorization: str = Header(None)):
    """
    Called by Vercel Cron every 15 minutes.
    Finds required events whose check-in window just closed and issues fines.
    """
    sb = get_supabase_admin()
    now = datetime.now(timezone.utc)

    events = (
        sb.table("events")
        .select("id")
        .eq("required", True)
        .lte("date", now.date().isoformat())
        .execute()
    ).data

    results = []
    for event in events:
        fines = await process_event_fines(event["id"])
        if fines:
            results.append({
                "event_id": event["id"],
                "fines_issued": len(fines),
            })

    return {"processed": len(results), "details": results}
