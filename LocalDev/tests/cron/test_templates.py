"""Outbox message templates — pure, no DB, no FastAPI. These always run.

Guards the copy every member actually receives: the registry must cover the whole
message_outbox event_type catalog, amounts must render from integer cents as
dollars, and an unknown event type must raise rather than silently produce an
empty message.
"""

from __future__ import annotations

import pytest

from api.cron.core import templates
from api.cron.core.templates import TemplateError, UnknownEventType, render

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
    [e for e in CATALOG if e not in ("ANNOUNCEMENT_SMS", "EVENT_NOTIFY")],
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
