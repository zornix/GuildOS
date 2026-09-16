"""SMTP provider adapter — the single outbound email boundary.

The twin of `api/announcements/services/twilio_client.py`: one function, raises
on failure, reads `api/config.py` settings and never `os.environ`. Everything
automatic in GuildOS goes out this way (setup/reset codes, treasury lifecycle,
jobs, security, event creation and role assignment); SMS is reserved for the two
manual announcement blasts — see docs/adr/0005.

Transport is stdlib `smtplib` + `email.message.EmailMessage`: Gmail / Google
Workspace SMTP on port 587 with STARTTLS and an app password. No new dependency
and no provider SDK — a transactional mail API can replace the body of
`send_email` the day volume outgrows the Workspace send limit.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from api.config import settings

_SMTP_TIMEOUT_SECONDS = 20.0


def _require(name: str) -> str:
    """Read a non-empty email setting or explain exactly what is missing."""
    value = (getattr(settings, name, "") or "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not configured; EMAIL_DELIVERY_MODE='smtp' requires "
            "SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD and EMAIL_FROM"
        )
    return value


def send_email(to: str, subject: str, text_body: str) -> None:
    """Send one plain-text email. Raises on any failure, like send_sms."""
    if not (to or "").strip():
        raise RuntimeError("send_email requires a destination address")

    host = _require("SMTP_HOST")
    user = _require("SMTP_USER")
    password = _require("SMTP_PASSWORD")
    sender = _require("EMAIL_FROM")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    reply_to = (settings.EMAIL_REPLY_TO or "").strip()
    if reply_to:
        message["Reply-To"] = reply_to
    message.set_content(text_body)

    with smtplib.SMTP(host, settings.SMTP_PORT, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(message)
