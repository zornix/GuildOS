"""
Short link generation + validation for event check-in.

Anti-cheat mechanism:
- Officer taps "Open Check-In" -> generates a short-lived link like:
    https://fraternityos.vercel.app/c/A7x9Kp
- Link is valid for N minutes (default 10), displayed on officer's phone
- Members physically present open the link on their own phone
- Link resolves to a check-in page that auto-submits with their session
- After TTL expires, link is dead -- no forwarding after the fact

Anti-forwarding measures:
1. Short TTL (configurable, default 10 min)
2. Officer can manually kill the link early
3. Audit log shows check-in timestamps for manual review
"""

import secrets
import string
from datetime import datetime, timezone, timedelta

from api.config import settings
from api.db import get_supabase_admin

ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 6


def generate_short_code() -> str:
    """Generate a 6-char alphanumeric code. ~56 billion possibilities."""
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


async def create_checkin_link(event_id: str, created_by: str) -> dict:
    """
    Create a new short-lived check-in link for an event.
    Deactivates any existing active link for the same event.
    """
    sb = get_supabase_admin()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.CHECKIN_LINK_TTL_MINUTES)

    sb.table("checkin_links") \
        .update({"active": False}) \
        .eq("event_id", event_id) \
        .eq("active", True) \
        .execute()

    for _ in range(5):
        code = generate_short_code()
        try:
            sb.table("checkin_links").insert({
                "event_id": event_id,
                "short_code": code,
                "created_by": created_by,
                "expires_at": expires_at.isoformat(),
                "active": True,
            }).execute()

            return {
                "short_code": code,
                "url": f"{settings.BASE_URL}/c/{code}",
                "expires_at": expires_at.isoformat(),
                "event_id": event_id,
            }
        except Exception:
            continue

    raise Exception("Failed to generate unique check-in code")


async def validate_checkin_link(short_code: str) -> dict | None:
    """Validate a short code. Returns event data if valid, None if expired/invalid."""
    sb = get_supabase_admin()
    now = datetime.now(timezone.utc)

    result = (
        sb.table("checkin_links")
        .select("*, events(*)")
        .eq("short_code", short_code)
        .eq("active", True)
        .gte("expires_at", now.isoformat())
        .single()
        .execute()
    )

    return result.data if result.data else None


async def deactivate_checkin_link(event_id: str):
    """Officer manually kills the link before TTL expires."""
    sb = get_supabase_admin()
    sb.table("checkin_links") \
        .update({"active": False}) \
        .eq("event_id", event_id) \
        .eq("active", True) \
        .execute()
