"""Health check helpers: DB ping with bounded retries."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from api.platform.postgres import PostgresClient


def retry_with_backoff(
    fn: Callable[[], None],
    *,
    max_attempts: int = 3,
    base_delay_sec: float = 0.15,
) -> Exception | None:
    """Run ``fn`` until success or ``max_attempts``; return last exception or None."""
    last: Exception | None = None
    for attempt in range(max_attempts):
        try:
            fn()
            return None
        except Exception as exc:
            last = exc
            if attempt < max_attempts - 1:
                time.sleep(base_delay_sec * (2**attempt))
    return last


def build_health_payload(
    client: PostgresClient,
    *,
    max_attempts: int = 3,
    base_delay_sec: float = 0.15,
    version: str = "0.1.0",
) -> dict[str, Any]:
    """
    Return JSON-serializable health body.

    - ``status``: ``error`` if DB ping fails; otherwise ``degraded`` for a stale cron.
    - ``checks.outbox_drain``: ``ok``, ``stale`` (older than 15 minutes), or ``unknown``.
    - ``checks.database``: ``ok`` or ``error`` (no raw exception text).
    """
    err = retry_with_backoff(client.ping, max_attempts=max_attempts, base_delay_sec=base_delay_sec)
    checks = {"database": "ok" if err is None else "error"}
    payload: dict[str, Any] = {
        "status": "ok" if err is None else "error",
        "version": version,
        "checks": checks,
    }
    if err is not None:
        payload["detail"] = "database_unreachable"
    else:
        outbox = "unknown"
        try:
            heartbeat = (
                client.table("cron_heartbeats").select("last_finished_at")
                .eq("job", "drain-outbox").maybe_single().execute()
            ).data
            if heartbeat:
                finished = heartbeat["last_finished_at"]
                if isinstance(finished, str):
                    finished = datetime.fromisoformat(finished.replace("Z", "+00:00"))
                outbox = "stale" if (datetime.now(timezone.utc) - finished).total_seconds() > 900 else "ok"
        except Exception:
            pass  # Heartbeat availability is not database readiness.
        checks["outbox_drain"] = outbox
        if outbox == "stale":
            payload["status"] = "degraded"
    return payload
