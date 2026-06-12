from __future__ import annotations

import json
import logging
from typing import Any

from postgrest.exceptions import APIError

logger = logging.getLogger(__name__)

def track(
    db: Any,
    chapter_id: str,
    member_id: str,
    event_name: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not event_name:
        raise ValueError("event_name is required")
        
    event_name = event_name[:120]
    metadata = metadata or {}
    
    try:
        # Check size of metadata roughly
        if len(json.dumps(metadata)) > 8000:
            metadata = {"_truncated": True}
    except Exception:
        metadata = {"_truncated": True}

    try:
        db.table("usage_events").insert(
            {
                "chapter_id": chapter_id,
                "member_id": member_id,
                "event_name": event_name,
                "metadata": metadata,
            }
        ).execute()
    except Exception as exc:
        # Fire and forget; if the insertion fails, we log it and move on.
        logger.warning(f"Failed to track usage event {event_name}: {exc}")

def summary(db: Any, chapter_id: str, days: int = 30) -> dict[str, Any]:
    # Use RPC or just query and aggregate. The simplest is a query if we can do date math.
    # Since we don't have a specific RPC mentioned, maybe we can just query usage_events where created_at >= now - days
    # Wait, PostgREST doesn't support aggregate count grouping easily without RPC, but we can just fetch and group in python if it's small, or use an RPC if available.
    # "Count usage_events for chapter in last N days"
    # To keep it simple, we can fetch the event_names from usage_events created in the last N days.
    from datetime import datetime, timedelta, timezone
    
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    resp = (
        db.table("usage_events")
        .select("event_name")
        .eq("chapter_id", chapter_id)
        .gte("created_at", cutoff.isoformat())
        .execute()
    )
    
    counts = {}
    for row in resp.data:
        counts[row["event_name"]] = counts.get(row["event_name"], 0) + 1
        
    return {
        "days": days,
        "counts": counts,
        "total": len(resp.data)
    }
