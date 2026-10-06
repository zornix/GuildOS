"""Outbox message templates — pure, no DB, no FastAPI. These always run.

Guards the copy every member actually receives: the registry must cover the whole
message_outbox event_type catalog, amounts must render from integer cents as
dollars, and an unknown event type must raise rather than silently produce an
empty message.
"""

from __future__ import annotations

import pytest

from api.platform import message_templates as templates
from api.platform.message_templates import TemplateError, UnknownEventType
from api.platform.message_templates import render as _render_with_footer


def render(event_type, payload=None, **kwargs) -> str:
    """The message body without its opt-out footer.

    Every body ends with the same sender/opt-out line (#57), which would make
    every copy assertion below restate it. The footer has its own tests instead.
    """
    return _render_with_footer(event_type, payload, **kwargs).rsplit("\n", 1)[0]

# The event_type CHECK catalog after 0070 + 0086 + 0131 + 0142 + 0143 + 0145,
# plus PAYMENT_REMINDER (0150). Every one must have a template.
CATALOG = [
    "INVOICE_ISSUED",
    "PAYMENT_APPROVED",
    "PAYMENT_REJECTED",
    "REFUND_ISSUED",
    "PAYMENT_REMINDER",
    "ANNOUNCEMENT_PUBLISHED",
    "ANNOUNCEMENT_SMS",
    "EVENT_NOTIFY",
    "JOB_REPORTED",
    "JOB_APPROVED",
    "JOB_REJECTED",
    "SECURITY_ASSIGNED",
    "SECURITY_SWAP_REQUESTED",
    "SECURITY_SWAP_ACCEPTED",
    "SECURITY_SWAP_DECLINED",
    # Email-only, added by 0159 (ADR-0005).
    "SETUP_CODE",
    "RESET_CODE",
    "EVENT_CREATED",
    "EVENT_ROLE_ASSIGNED",
]

# Minimal payloads that exercise the fully-populated branch of each template.
FULL_PAYLOADS = {
    "INVOICE_ISSUED": {"amount_cents": 2500, "kind": "fine", "description": "Missed meeting"},
    "PAYMENT_APPROVED": {"claimed_amount_cents": 5000},
    "PAYMENT_REJECTED": {"claimed_amount_cents": 5000},
    "REFUND_ISSUED": {"amount_cents": 2000, "reason": "overpayment"},
    "PAYMENT_REMINDER": {"unpaid_count": 3, "unpaid_total_cents": 7500},
    "ANNOUNCEMENT_PUBLISHED": {"title": "Chapter meeting moved"},
    "ANNOUNCEMENT_SMS": {"body": "Dues due Friday."},
    "EVENT_NOTIFY": {"body": "Formal — 2026-09-01 19:00. 3 open jobs."},
    "JOB_REPORTED": {"title": "Setup crew"},
    "JOB_APPROVED": {"title": "Setup crew"},
    "JOB_REJECTED": {"title": "Setup crew", "reason": "photo missing"},
    "SECURITY_ASSIGNED": {"title": "Security shift", "event_date": "2026-09-01"},
    "SECURITY_SWAP_REQUESTED": {"note": "family emergency"},
    "SECURITY_SWAP_ACCEPTED": {},
    "SECURITY_SWAP_DECLINED": {},
    "SETUP_CODE": {
        "code": "AB12CD",
        "expires_at": "2026-09-22T00:00:00+00:00",
        "frontend_url": "https://app.guildos.example",
    },
    "RESET_CODE": {
        "code": "AB12CD",
        "expires_at": "2026-09-22T00:00:00+00:00",
        "frontend_url": "https://app.guildos.example",
    },
    "EVENT_CREATED": {
        "title": "Rush Kickoff",
        "date": "2026-10-01",
        "time": "18:00",
        "location": "The House",
    },
    "EVENT_ROLE_ASSIGNED": {
        "title": "Rush Kickoff",
        "date": "2026-10-01",
        "role": "organizer",
    },
}


def test_registry_covers_the_whole_event_catalog():
    assert set(CATALOG) <= set(templates.TEMPLATES)


@pytest.mark.parametrize("event_type", CATALOG)
def test_every_template_renders_a_non_empty_body(event_type):
    body = render(event_type, FULL_PAYLOADS[event_type])
    assert body.strip()
    assert "None" not in body  # no leaked Python None in member-facing copy
    assert "{" not in body  # no unformatted placeholder


@pytest.mark.parametrize(
    "event_type",
    [
        e
        for e in CATALOG
        # The pass-through and code templates have nothing to degrade to: an
        # empty body or a missing code is a failure, not a weaker sentence.
        if e not in ("ANNOUNCEMENT_SMS", "EVENT_NOTIFY", "SETUP_CODE", "RESET_CODE")
    ],
)
def test_templates_degrade_on_an_empty_payload(event_type):
    """A missing optional field weakens the sentence; it never crashes."""
    assert render(event_type, {}).strip()


# ── Money rendering (integer cents -> dollars) ───────────────────────────────


def test_invoice_issued_renders_cents_as_dollars():
    body = render("INVOICE_ISSUED", FULL_PAYLOADS["INVOICE_ISSUED"])
    assert body == "New charge: $25.00 — Missed meeting. Log in to view."


def test_invoice_issued_without_description_falls_back_to_kind():
    body = render("INVOICE_ISSUED", {"amount_cents": 12345, "kind": "dues"})
    assert body == "New charge: $123.45 — dues. Log in to view."


def test_payment_approved_renders_amount():
    assert render("PAYMENT_APPROVED", {"claimed_amount_cents": 5000}) == (
        "Payment recorded: $50.00. Thank you."
    )


def test_refund_issued_renders_amount():
    assert render("REFUND_ISSUED", {"amount_cents": 2000}) == (
        "Refund issued: $20.00. Log in to view."
    )


def test_zero_and_sub_dollar_amounts_render_with_two_decimals():
    assert "$0.07" in render("REFUND_ISSUED", {"amount_cents": 7})


def test_float_amount_is_rejected_not_silently_rounded():
    with pytest.raises(TemplateError):
        render("INVOICE_ISSUED", {"amount_cents": 25.5})


# ── Reminder pluralization ───────────────────────────────────────────────────


def test_payment_reminder_plural():
    assert render("PAYMENT_REMINDER", {"unpaid_count": 3, "unpaid_total_cents": 7500}) == (
        "Reminder: 3 unpaid charges totaling $75.00. Log in to pay."
    )


def test_payment_reminder_singular():
    assert render("PAYMENT_REMINDER", {"unpaid_count": 1, "unpaid_total_cents": 2500}) == (
        "Reminder: 1 unpaid charge totaling $25.00. Log in to pay."
    )


# ── Pass-through bodies ──────────────────────────────────────────────────────


def test_announcement_sms_passes_the_senders_body_through_verbatim():
    assert render("ANNOUNCEMENT_SMS", {"body": "Dues due Friday."}) == "Dues due Friday."


def test_event_notify_passes_the_body_through_verbatim():
    body = "Formal — 2026-09-01 19:00. 3 open jobs."
    assert render("EVENT_NOTIFY", {"body": body}) == body


def test_passthrough_without_a_body_raises():
    with pytest.raises(TemplateError):
        render("ANNOUNCEMENT_SMS", {})


# ── Failure modes ────────────────────────────────────────────────────────────


def test_unknown_event_type_raises():
    with pytest.raises(UnknownEventType):
        render("NOT_A_REAL_EVENT", {})


def test_none_payload_is_tolerated():
    assert render("JOB_APPROVED", None).strip()


def test_job_rejected_includes_the_reason():
    assert render("JOB_REJECTED", {"title": "Setup crew", "reason": "photo missing"}) == (
        "Job sent back: Setup crew — photo missing. Log in for details."
    )


# ── Sender identification + opt-out footer (#57) ─────────────────────────────


@pytest.mark.parametrize("event_type", CATALOG)
def test_every_rendered_body_ends_with_the_opt_out_line(event_type):
    body = _render_with_footer(event_type, FULL_PAYLOADS[event_type], chapter_name="Beta Theta")
    assert body.endswith("— GuildOS for Beta Theta. Reply STOP to opt out.")


def test_the_footer_degrades_without_a_chapter_name():
    assert templates.footer("") == "— GuildOS. Reply STOP to opt out."
    assert templates.footer(None) == "— GuildOS. Reply STOP to opt out."
    assert _render_with_footer("JOB_APPROVED", {}).endswith(templates.footer(None))


# ── Channel (ADR-0005) ───────────────────────────────────────────────────────


def test_email_bodies_carry_no_opt_out_line():
    body = _render_with_footer("JOB_APPROVED", {"title": "X"}, chapter_name="Delta", channel="email")
    assert body.endswith("— GuildOS for Delta.")
    assert "Reply STOP" not in body


def test_sms_bodies_still_carry_the_opt_out_line():
    body = _render_with_footer("JOB_APPROVED", {"title": "X"}, chapter_name="Delta")
    assert body.endswith("— GuildOS for Delta. Reply STOP to opt out.")


@pytest.mark.parametrize("event_type", CATALOG)
def test_every_event_type_has_an_email_subject(event_type):
    subject, body = templates.render_email(event_type, FULL_PAYLOADS[event_type])
    assert subject and subject != "GuildOS"
    assert body.strip()


def test_a_setup_code_body_says_where_to_go_and_when_it_expires():
    _, body = templates.render_email("SETUP_CODE", FULL_PAYLOADS["SETUP_CODE"])
    assert "AB12CD" in body
    assert "https://app.guildos.example" in body
    assert "I have a setup code" in body
    assert "2026-09-22" in body


def test_a_code_payload_without_a_code_fails_loudly():
    with pytest.raises(TemplateError):
        render("SETUP_CODE", {"frontend_url": "https://x"})


def test_announcements_do_not_import_cron():
    """Shared rendering must not create an announcements/cron package cycle."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "api" / "announcements"
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("api.cron"), str(path)
            elif isinstance(node, ast.Import):
                assert all(not name.name.startswith("api.cron") for name in node.names), str(path)
