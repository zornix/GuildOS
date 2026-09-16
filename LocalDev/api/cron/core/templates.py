"""Message templates for the outbox drain — pure, no I/O, no settings.

One callable per `message_outbox.event_type`, each turning that event's payload
into the SMS body a member actually receives. Kept in `core/` (the domain's
no-I/O layer) so the copy is unit-testable without a database, a provider, or
FastAPI.

The catalog mirrors `message_outbox_event_type_check` after 0070 + 0086 + 0131 +
0142 + 0143 + 0145, plus PAYMENT_REMINDER (0150). Producers:

  INVOICE_ISSUED / PAYMENT_APPROVED / PAYMENT_REJECTED / REFUND_ISSUED
      api/treasury/notifications.py
  PAYMENT_REMINDER
      api/treasury/notifications.py::enqueue_payment_reminder (0150)
  ANNOUNCEMENT_PUBLISHED   migrations/0086, ANNOUNCEMENT_SMS  migrations/0132
  JOB_REPORTED/APPROVED/REJECTED   migrations/0142, 0144
  EVENT_NOTIFY             migrations/0143
  SECURITY_ASSIGNED / SECURITY_SWAP_REQUESTED / _ACCEPTED / _DECLINED
      migrations/0145

Copy rules: neutral and actionable, no shaming, no invented facts. Amounts arrive
as integer cents and are rendered through Money (CLAUDE.md: money is always
integer cents; never a float path). A missing optional field degrades the
sentence rather than raising.

Channel (0159 / ADR-0005): the same template renders both channels; only the
footer differs. `render(..., channel="sms")` keeps the STOP line the carriers
require; `render_email` returns (subject, body) with a plain sender line.
SETUP_CODE / RESET_CODE / EVENT_CREATED / EVENT_ROLE_ASSIGNED are email-only.

ANNOUNCEMENT_SMS and EVENT_NOTIFY carry a `body` composed upstream (the
announcement text / the event notify line); those templates pass it through
verbatim rather than re-writing an officer's words.
"""

from __future__ import annotations

from typing import Callable

from api.treasury.core.money import Money


class UnknownEventType(Exception):
    """No template is registered for this message_outbox.event_type."""


class TemplateError(Exception):
    """The payload did not carry what the template needs to render."""


_APP_CTA = "Log in to view."


def _dollars(payload: dict, key: str) -> str | None:
    """Integer cents -> '$12.34', or None when the amount is absent/unusable."""
    cents = payload.get(key)
    if cents is None:
        return None
    if isinstance(cents, bool) or not isinstance(cents, int):
        raise TemplateError(f"{key} must be integer cents, got {cents!r}")
    return Money(cents).to_dollars_str()


def _text(payload: dict, key: str) -> str:
    return str(payload.get(key) or "").strip()


# ── Treasury ─────────────────────────────────────────────────────────────────


def _invoice_issued(p: dict) -> str:
    amount = _dollars(p, "amount_cents")
    what = _text(p, "description") or _text(p, "kind") or "charge"
    if amount:
        return f"New charge: {amount} — {what}. {_APP_CTA}"
    return f"New charge: {what}. {_APP_CTA}"


def _payment_approved(p: dict) -> str:
    amount = _dollars(p, "claimed_amount_cents") or _dollars(p, "amount_cents")
    if amount:
        return f"Payment recorded: {amount}. Thank you."
    return "Payment recorded. Thank you."


def _payment_rejected(p: dict) -> str:
    amount = _dollars(p, "claimed_amount_cents") or _dollars(p, "amount_cents")
    if amount:
        return f"Your payment of {amount} was not approved. Log in for details."
    return "Your payment was not approved. Log in for details."


def _refund_issued(p: dict) -> str:
    amount = _dollars(p, "amount_cents")
    if amount:
        return f"Refund issued: {amount}. {_APP_CTA}"
    return f"Refund issued. {_APP_CTA}"


def _payment_reminder(p: dict) -> str:
    """A reminder for nothing owed is not a reminder.

    Zero renders as the *truthy* string "$0.00", so a zero count or a zero total
    used to sail past the guards below and demand payment of $0.00 (issue #35).
    The producer no longer enqueues those (api/memberadmin/api/scores.py); a row
    that reaches here anyway fails loudly instead of texting a member nonsense.
    """
    count = p.get("unpaid_count")
    total_cents = p.get("unpaid_total_cents")
    if count == 0 or total_cents == 0:
        raise TemplateError("nothing outstanding — no reminder to render")

    total = _dollars(p, "unpaid_total_cents")
    if isinstance(count, int) and not isinstance(count, bool) and total:
        noun = "charge" if count == 1 else "charges"
        return f"Reminder: {count} unpaid {noun} totaling {total}. Log in to pay."
    if total:
        return f"Reminder: {total} in unpaid charges. Log in to pay."
    return "Reminder: you have unpaid charges. Log in to pay."


# ── Announcements / events ───────────────────────────────────────────────────


def _announcement_published(p: dict) -> str:
    title = _text(p, "title")
    if title:
        return f"New announcement: {title}. Log in to read."
    return "New announcement posted. Log in to read."


def _passthrough_body(p: dict) -> str:
    """ANNOUNCEMENT_SMS / EVENT_NOTIFY: the body was composed by the sender."""
    body = _text(p, "body")
    if not body:
        raise TemplateError("payload has no 'body'")
    return body


# ── Jobs (tasks) ─────────────────────────────────────────────────────────────


def _job_reported(p: dict) -> str:
    title = _text(p, "title") or "A job"
    return f"Job reported for review: {title}. Log in to approve or reject."


def _job_approved(p: dict) -> str:
    title = _text(p, "title") or "your job"
    return f"Job approved: {title}. Credit recorded."


def _job_rejected(p: dict) -> str:
    title = _text(p, "title") or "your job"
    reason = _text(p, "reason")
    if reason:
        return f"Job sent back: {title} — {reason}. Log in for details."
    return f"Job sent back: {title}. Log in for details."


# ── Security shifts / swaps ──────────────────────────────────────────────────


def _security_assigned(p: dict) -> str:
    title = _text(p, "title")
    when = _text(p, "event_date")
    if title and when:
        return f"Security shift assigned: {title} on {when}. Log in for details."
    if title:
        return f"Security shift assigned: {title}. Log in for details."
    return "You were assigned a security shift. Log in for details."


def _security_removed(p: dict) -> str:
    # Not currently reachable: 0145 records SECURITY_REMOVED in audit_logs only
    # and the outbox event_type CHECK does not include it. Registered so the
    # drain renders correctly the day a producer starts enqueueing it.
    return "You were removed from a security shift. Log in for details."


def _swap_requested(p: dict) -> str:
    note = _text(p, "note")
    if note:
        return f"Security swap requested — {note}. Log in to accept or decline."
    return "A security swap was requested with you. Log in to accept or decline."


def _swap_accepted(p: dict) -> str:
    return "Your security swap was accepted. Log in to see the updated shift."


def _swap_declined(p: dict) -> str:
    return "Your security swap was declined — you still hold the shift. Log in for details."


# ── Account codes (email only) ───────────────────────────────────────────────


def _setup_code(p: dict) -> str:
    """SETUP_CODE / RESET_CODE: the code plus what to do with it.

    `frontend_url` is inlined by the producer (api/auth/notifications.py) rather
    than read from settings here — this module stays pure.
    """
    code = _text(p, "code")
    if not code:
        raise TemplateError("payload has no 'code'")
    where = _text(p, "frontend_url") or "the GuildOS site"
    expires = _text(p, "expires_at")[:10]
    lines = [
        f"Your GuildOS code is {code}.",
        "",
        f"Go to {where}, choose \"I have a setup code\", and enter it to finish "
        "setting up your account.",
    ]
    if expires:
        lines.append(f"The code expires {expires}.")
    return "\n".join(lines)


# ── Events (email only) ──────────────────────────────────────────────────────


def _event_created(p: dict) -> str:
    title = _text(p, "title") or "A new event"
    when = " ".join(x for x in (_text(p, "date"), _text(p, "time")) if x)
    where = _text(p, "location")
    line = f"New event: {title}"
    if when:
        line += f" — {when}"
    if where:
        line += f" at {where}"
    return f"{line}. {_APP_CTA}"


def _event_role_assigned(p: dict) -> str:
    role = _text(p, "role") or "helper"
    title = _text(p, "title") or "an event"
    when = _text(p, "date")
    line = f"You were assigned as {role} for {title}"
    if when:
        line += f" on {when}"
    return f"{line}. Log in for details."


TEMPLATES: dict[str, Callable[[dict], str]] = {
    "INVOICE_ISSUED": _invoice_issued,
    "PAYMENT_APPROVED": _payment_approved,
    "PAYMENT_REJECTED": _payment_rejected,
    "REFUND_ISSUED": _refund_issued,
    "PAYMENT_REMINDER": _payment_reminder,
    "ANNOUNCEMENT_PUBLISHED": _announcement_published,
    "ANNOUNCEMENT_SMS": _passthrough_body,
    "EVENT_NOTIFY": _passthrough_body,
    "JOB_REPORTED": _job_reported,
    "JOB_APPROVED": _job_approved,
    "JOB_REJECTED": _job_rejected,
    "SECURITY_ASSIGNED": _security_assigned,
    "SECURITY_REMOVED": _security_removed,
    "SECURITY_SWAP_REQUESTED": _swap_requested,
    "SECURITY_SWAP_ACCEPTED": _swap_accepted,
    "SECURITY_SWAP_DECLINED": _swap_declined,
    "SETUP_CODE": _setup_code,
    "RESET_CODE": _setup_code,
    "EVENT_CREATED": _event_created,
    "EVENT_ROLE_ASSIGNED": _event_role_assigned,
}

# Email subject lines. One static phrase per event type: the body carries the
# specifics, and a subject that restates them just gets truncated in the client.
SUBJECTS: dict[str, str] = {
    "INVOICE_ISSUED": "New charge on your account",
    "PAYMENT_APPROVED": "Payment recorded",
    "PAYMENT_REJECTED": "Payment not approved",
    "REFUND_ISSUED": "Refund issued",
    "PAYMENT_REMINDER": "You have unpaid charges",
    "ANNOUNCEMENT_PUBLISHED": "New chapter announcement",
    "ANNOUNCEMENT_SMS": "New chapter announcement",
    "EVENT_NOTIFY": "Chapter event update",
    "JOB_REPORTED": "A job is waiting for your review",
    "JOB_APPROVED": "Job approved",
    "JOB_REJECTED": "Job sent back",
    "SECURITY_ASSIGNED": "You have a security shift",
    "SECURITY_REMOVED": "Security shift removed",
    "SECURITY_SWAP_REQUESTED": "Security swap requested",
    "SECURITY_SWAP_ACCEPTED": "Security swap accepted",
    "SECURITY_SWAP_DECLINED": "Security swap declined",
    "SETUP_CODE": "Your GuildOS setup code",
    "RESET_CODE": "Your GuildOS reset code",
    "EVENT_CREATED": "New chapter event",
    "EVENT_ROLE_ASSIGNED": "You were assigned to an event",
}


def footer(chapter_name: str | None = None, *, channel: str = "sms") -> str:
    """The sender identification + opt-out line every outbound message carries.

    Twilio and the carriers require an SMS campaign to say who is texting and how
    to stop (#57). One line, appended to every body rather than written into each
    template, so no template can be added without it.

    Email carries no opt-out line: STOP is a carrier mechanism, and these are
    transactional messages to members of a chapter they belong to (ADR-0005).
    """
    who = (chapter_name or "").strip()
    stop = " Reply STOP to opt out." if channel == "sms" else ""
    who_part = f"— GuildOS for {who}." if who else "— GuildOS."
    return f"{who_part}{stop}"


def render(
    event_type: str,
    payload: dict | None,
    *,
    chapter_name: str | None = None,
    channel: str = "sms",
) -> str:
    """Render one outbox row's message body, footer included.

    Raises UnknownEventType for an unregistered event_type and TemplateError when
    the payload is unusable. The drain catches both and marks the row 'failed'
    with the message in `last_error`, so one bad row never kills the batch.
    """
    template = TEMPLATES.get(event_type)
    if template is None:
        raise UnknownEventType(f"no message template for event_type {event_type!r}")
    try:
        body = template(payload or {})
    except (TemplateError, UnknownEventType):
        raise
    except Exception as exc:  # a template bug must not escape as an opaque crash
        raise TemplateError(f"{type(exc).__name__}: {exc}") from exc
    if not body:
        raise TemplateError(f"template for {event_type!r} produced an empty body")
    return f"{body}\n{footer(chapter_name, channel=channel)}"


def render_email(
    event_type: str, payload: dict | None, *, chapter_name: str | None = None
) -> tuple[str, str]:
    """(subject, body) for an email-channel outbox row."""
    body = render(event_type, payload, chapter_name=chapter_name, channel="email")
    return SUBJECTS.get(event_type, "GuildOS"), body
