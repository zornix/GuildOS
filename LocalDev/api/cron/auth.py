"""Cron authentication — the shared-secret gate on every scheduled endpoint.

GTMLarpChecklist 3.6: `CRON_SECRET` was declared in api/config.py and referenced
by zero other lines, while the config comment and .env.example both claimed
"empty -> the endpoint returns 401". It didn't; the cron routes had no auth
dependency of any kind. This makes the claim true.

Contract (matches what Vercel Cron sends: `Authorization: Bearer $CRON_SECRET`):

  * `settings.CRON_SECRET` empty/unset  -> 401, always. An unconfigured deploy
    cannot have its cron endpoints triggered by anyone, including with an empty
    or absent header.
  * header missing or not an exact match -> 401.
  * comparison is constant-time (hmac.compare_digest) so the secret cannot be
    recovered by timing the endpoint.

The 401 detail is deliberately uniform — it never reveals which check failed.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from api.config import settings

_UNAUTHORIZED = "Unauthorized"


async def require_cron_secret(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: allow the request only for the configured cron caller."""
    # Read through the settings object at call time so config changes (and test
    # monkeypatching) take effect without re-importing the module.
    secret = (settings.CRON_SECRET or "").strip()
    if not secret:
        # No secret configured => cron is disabled, not open.
        raise HTTPException(401, _UNAUTHORIZED)
    if not authorization:
        raise HTTPException(401, _UNAUTHORIZED)
    if not hmac.compare_digest(authorization, f"Bearer {secret}"):
        raise HTTPException(401, _UNAUTHORIZED)
