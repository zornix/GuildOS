"""Twilio REST provider adapter — the single outbound SMS boundary.

Extracted from api/announcements/services/sms.py so both delivery paths share one
implementation: the inline announcement/event dispatch (`sms.dispatch_send`) and
the scheduled outbox drain (`api/cron/services/outbox_drain.py`).

Configuration comes from `api/config.py` (never `os.environ`), so every credential
is part of the settings surface and the production boot guard. A missing or empty
setting raises a RuntimeError naming it — never a bare KeyError that a caller's
`except Exception` would silently record as "failed" (GTMLarpChecklist 2.3).

TODO(ops): verify A2P 10DLC campaign registration covers application-initiated
SMS before enabling MESSAGE_DELIVERY_MODE=twilio. Unregistered traffic is
carrier-blocked.
"""

from __future__ import annotations

from api.config import settings

_TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
_HTTP_TIMEOUT_SECONDS = 15.0


def _require(name: str) -> str:
    """Read a non-empty TWILIO_* setting or explain exactly what is missing."""
    value = (getattr(settings, name, "") or "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not configured; MESSAGE_DELIVERY_MODE='twilio' requires "
            "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER"
        )
    return value


def send_sms(to_e164: str, body: str) -> None:
    """POST one SMS to the Twilio REST API. Raises on any failure; returns None.

    `to_e164` is expected to already be E.164 (members.phone is normalized at
    write time); this adapter does not reformat numbers.
    """
    import httpx

    account_sid = _require("TWILIO_ACCOUNT_SID")
    auth_token = _require("TWILIO_AUTH_TOKEN")
    from_number = _require("TWILIO_FROM_NUMBER")

    if not (to_e164 or "").strip():
        raise RuntimeError("send_sms requires a destination number")

    resp = httpx.post(
        _TWILIO_MESSAGES_URL.format(sid=account_sid),
        data={"To": to_e164, "From": from_number, "Body": body},
        auth=(account_sid, auth_token),
        timeout=_HTTP_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
