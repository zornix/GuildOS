"""Clock — the single source of "now" (tz-aware UTC). Frozen contract §2.3.

No `datetime.now()` / SQL `now()` scattered through Treasury code: everything
timestamped takes a Clock so tests can pin time with FakeClock.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:  # tz-aware UTC
        ...


class SystemClock:
    """Real clock — wall-clock time in UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock:
    """Deterministic clock for tests; returns a fixed tz-aware instant."""

    def __init__(self, fixed: datetime):
        if fixed.tzinfo is None:
            raise ValueError("FakeClock requires a tz-aware datetime")
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed
