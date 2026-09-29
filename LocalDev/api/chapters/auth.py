"""Who may create a chapter (#74).

Two callers, both allowed:

  * **ops** — `Authorization: Bearer $PLATFORM_SECRET`. Same fail-closed,
    constant-time contract as `CRON_SECRET` (`api/cron/auth.py`): an unset
    secret means the header can never match, and a presented-but-wrong header
    is 401 rather than a silent downgrade to the bootstrap path.
  * **bootstrap** — no header at all, rate-limited per source IP. This is the
    first officer signing their own chapter up; requiring the secret here would
    put a human in the loop for every signup, which is the thing #74 removes.
"""

from __future__ import annotations

import hmac
import time

from fastapi import HTTPException, Request

from api.auth.api.auth import _client_ip as _trusted_client_ip
from api.config import settings

_UNAUTHORIZED = "Unauthorized"

# ponytail: in-process sliding window — per worker, lost on a serverless cold
# start, so the real ceiling is (workers x limit). It stops a script, not a
# botnet. Move to a `login_attempts`-style table if abuse shows up in the wild.
_WINDOW_SECONDS = 60 * 60
_MAX_PER_IP = 3
_MAX_TOTAL = 20
_recent: list[tuple[float, str]] = []


def _client_ip(request: Request | None) -> str:
    # Rightmost-trusted X-Forwarded-For, same as the login limiter.
    return _trusted_client_ip(request) or "unknown"


def _rate_limit(ip: str) -> None:
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS
    _recent[:] = [entry for entry in _recent if entry[0] > cutoff]
    if len(_recent) >= _MAX_TOTAL or sum(1 for e in _recent if e[1] == ip) >= _MAX_PER_IP:
        raise HTTPException(429, "Too many chapter signups — try again later")
    _recent.append((now, ip))


def authorize_chapter_create(request: Request, authorization: str | None) -> None:
    """Allow the request, or raise. Read `settings` at call time so tests can
    monkeypatch the secret without re-importing."""
    if authorization:
        secret = (settings.PLATFORM_SECRET or "").strip()
        if not secret or not hmac.compare_digest(authorization, f"Bearer {secret}"):
            raise HTTPException(401, _UNAUTHORIZED)
        return
    _rate_limit(_client_ip(request))
