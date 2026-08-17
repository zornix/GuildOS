"""Health check helpers: DB ping with bounded retries."""

from __future__ import annotations

import time
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

    - ``status``: ``ok`` if DB ping succeeds after retries, else ``error``.
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
    return payload
