"""Auth's outbox enqueue helpers — setup and reset codes by email (ADR-0005).

Every code-issuing endpoint still *returns* the plaintext code (the officer UI
shows it as a hand-over fallback); this queues the same code as an email so the
member can act without anyone reading it out loud.

The code lives in the outbox payload, which is how the drain renders it. That
makes the payload a credential: the officer-facing outbox list
(api/announcements/services/outbox.py) refuses to render these two event types,
and the drain wipes the payload to `{}` on both sent and failed rows
(api/cron/services/outbox_drain.py). These code rows cannot be retried under
D21; issue a new setup or reset code instead.

`frontend_url` is inlined here rather than read inside the template — the
template module is pure and settings-free.
"""

from __future__ import annotations

import logging

from api.config import settings
from api.platform.outbox import enqueue

logger = logging.getLogger(__name__)

SETUP_CODE = "SETUP_CODE"
RESET_CODE = "RESET_CODE"


def notify_code(
    sb,
    *,
    event_type: str,
    chapter_id: str,
    member_id: str,
    code: str,
    expires_at: str,
) -> dict | None:
    """Queue a code email; transaction failures must roll back its issuance.

    Outside transactions, preserve the invite even if email enqueue fails.
    """
    try:
        return enqueue(
            sb,
            channel="email",
            event_type=event_type,
            chapter_id=chapter_id,
            member_id=member_id,
            target_table="members",
            target_id=member_id,
            # A member can be re-invited or reset repeatedly; the issuance time
            # is what makes each one a distinct message.
            dedup_key=f"{event_type}:{member_id}:{expires_at}",
            payload={
                "code": code,
                "expires_at": expires_at,
                "frontend_url": settings.FRONTEND_URL,
            },
        )
    except Exception as exc:
        if getattr(getattr(sb, "_pool", None), "in_tx", False):
            raise
        # No exc_info, and the message is scrubbed: a DB error quotes the
        # statement it failed on, and that statement carries the code. Logs are
        # a wider readership than the outbox, which already hides these rows.
        logger.warning(
            "could not enqueue %s for member %s: %s",
            event_type,
            member_id,
            f"{type(exc).__name__}: {exc}".replace(code, "***"),
        )
        return None
