"""Usage instrumentation — bounded event track + a bounded read model."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ponytail: one extra indexed COUNT per tracked event; move to a windowed counter if tracking volume ever matters.
MAX_EVENTS_PER_MEMBER_PER_HOUR = 600
_EVENT_NAME = re.compile(r"[a-z0-9_.:\-]{1,64}")
_METADATA_MAX_BYTES = 1000

# The client abstraction (api/platform/postgres.py, mimicking supabase-py) has no
# GROUP BY: only filters, ordering, limit, and an exact COUNT(*). So the total
# is aggregated in SQL via count='exact' (the count query ignores LIMIT), while
# the per-event-name breakdown is computed over a capped page of rows.
_SUMMARY_ROW_CAP = 10_000


def track(
    db: Any,
    chapter_id: str,
    member_id: str,
    event_name: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not event_name:
        raise ValueError("event_name is required")
    if _EVENT_NAME.fullmatch(event_name) is None:
        return

    metadata = metadata or {}
    try:
        encoded = json.dumps(metadata).encode()
        if len(encoded) > _METADATA_MAX_BYTES:
            metadata = {"_truncated": True}
    except Exception:
        metadata = {"_truncated": True}

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        existing = (
            db.table("usage_events")
            .select("id", count="exact")
            .eq("member_id", member_id)
            .gte("created_at", cutoff)
            .limit(1)
            .execute()
        )
        if (existing.count or 0) >= MAX_EVENTS_PER_MEMBER_PER_HOUR:
            return
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
    """Per-event-name usage counts for the chapter's last `days` days.

    `total` is the exact chapter total for the window. `counts` is derived from
    at most _SUMMARY_ROW_CAP rows; when the window is larger than that,
    `truncated` is True and `counts` describes the newest capped page only.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    resp = (
        db.table("usage_events")
        .select("event_name", count="exact")
        .eq("chapter_id", chapter_id)
        .gte("created_at", cutoff.isoformat())
        .order("created_at", desc=True)
        .limit(_SUMMARY_ROW_CAP)
        .execute()
    )

    rows = resp.data or []
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["event_name"]] = counts.get(row["event_name"], 0) + 1

    total = resp.count if resp.count is not None else len(rows)
    return {
        "days": days,
        "counts": counts,
        "total": total,
        "truncated": total > len(rows),
        "counted_rows": len(rows),
    }
