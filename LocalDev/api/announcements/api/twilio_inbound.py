"""POST /api/twilio/inbound — the STOP/START/HELP webhook (#57).

Twilio POSTs a form-encoded body here whenever someone replies to one of our
messages. There is no JWT: the caller is Twilio, not a member, so the request is
authenticated by `X-Twilio-Signature` — an HMAC-SHA1, keyed on TWILIO_AUTH_TOKEN,
over the public URL concatenated with every POST parameter sorted by name. An
unsigned or mismatched request is a 403; an unset auth token fails closed, since
"no token configured" must never mean "anyone may opt the roster out".

The Messaging Service's **Advanced Opt-Out** already handles the carrier side —
Twilio stops delivering to a number that texted STOP and sends the confirmation
reply itself. This webhook exists so *our* database knows too: otherwise every
subsequent send still queues a row for a member who will never receive it, and
nothing in the product shows an officer why.

Mounted on its own /api/twilio prefix rather than under /api/announcements
because it is a provider callback, not part of the announcements surface.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response

from api.config import settings
from api.phone import to_e164
from api.platform.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

_EMPTY_TWIML = "<?xml version='1.0' encoding='UTF-8'?><Response/>"
_HELP_TEXT = "GuildOS chapter notifications. Reply STOP to opt out. Msg&data rates may apply."

# Twilio's documented opt-out / opt-in keywords, matched case-insensitively on
# the trimmed body. Anything else is just a reply we have nowhere to put.
_STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
_START_WORDS = {"start", "yes", "unstop"}
_HELP_WORDS = {"help", "info"}


def _twiml(message: str | None = None) -> Response:
    body = (
        _EMPTY_TWIML
        if message is None
        else f"<?xml version='1.0' encoding='UTF-8'?><Response><Message>{message}</Message></Response>"
    )
    return Response(content=body, media_type="application/xml")


def expected_signature(url: str, params: dict[str, str], auth_token: str) -> str:
    """Twilio's request-signature scheme: base64(HMAC-SHA1(token, url + sorted kv))."""
    data = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(
        auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _verify(request: Request, params: dict[str, str]) -> None:
    token = (settings.TWILIO_AUTH_TOKEN or "").strip()
    if not token:
        # Fail closed. An open webhook lets anyone opt any number out.
        logger.error("twilio inbound rejected: TWILIO_AUTH_TOKEN is not configured")
        raise HTTPException(403, "Signature verification unavailable")

    # The signature covers the URL Twilio was configured with, which is our public
    # origin — not whatever Host header reached the function behind Vercel's proxy.
    url = settings.BASE_URL.rstrip("/") + request.url.path
    supplied = request.headers.get("X-Twilio-Signature", "")
    if not hmac.compare_digest(supplied, expected_signature(url, params, token)):
        raise HTTPException(403, "Bad Twilio signature")


@router.post("/inbound")
async def twilio_inbound(request: Request):
    """Record STOP / START / HELP from an inbound SMS.

    Always answers with TwiML: empty for anything we have no reply for, a single
    Message for HELP. Twilio retries on a non-2xx, so an unrecognized body is a
    200 with an empty <Response/>, not an error.
    """
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    _verify(request, params)

    phone = to_e164(params.get("From", ""))
    word = (params.get("Body") or "").strip().lower()
    if not phone:
        return _twiml()

    sb = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Every member holding that number, across chapters: the person who texted
    # STOP means the number, not one membership row.
    if word in _STOP_WORDS:
        sb.table("members").update({"sms_opted_out_at": now}).eq("phone", phone).execute()
    elif word in _START_WORDS:
        sb.table("members").update(
            {"sms_opted_out_at": None, "sms_consent_at": now}
        ).eq("phone", phone).execute()
    elif word in _HELP_WORDS:
        return _twiml(_HELP_TEXT)

    return _twiml()
