"""The email channel of the outbox drain (ADR-0005, migration 0159).

Everything automatic is email; SMS is only the two manual announcement blasts.
These cover the routing decision itself, the `no_email` failure, the dry_run
simulation, and that the SMTP adapter really builds the message we expect.
"""

from __future__ import annotations

import smtplib

import pytest

from api.cron.services.outbox_drain import drain_outbox


@pytest.fixture
def drain(sb_client, chapter_id):
    def _drain(**kwargs):
        return drain_outbox(sb_client, chapter_id=chapter_id, **kwargs)

    return _drain


@pytest.fixture
def fake_twilio(monkeypatch):
    """Capture what would go to Twilio instead of calling it."""
    sent: list = []
    monkeypatch.setattr(
        "api.announcements.services.twilio_client.send_sms",
        lambda to, body: sent.append((to, body)),
    )
    return sent


@pytest.fixture
def member_with_email(member_factory, cursor):
    def _make(email: str | None = None) -> str:
        m = member_factory()
        cursor.execute(
            "UPDATE members SET email = %s WHERE id = %s",
            (email or f"drain-{m}@example.test", m),
        )
        return m

    return _make


def test_email_row_goes_to_smtp_not_twilio(
    drain, outbox_row, read_outbox, email_mode, member_with_email, fake_email, fake_twilio
):
    email_mode("smtp")
    member = member_with_email()
    row = outbox_row(
        event_type="JOB_APPROVED",
        channel="email",
        member_id=member,
        payload={"title": "Setup crew"},
    )

    assert drain()["sent"] == 1
    assert read_outbox(row["id"])["status"] == "sent"
    assert fake_twilio == []

    to, subject, body = fake_email[0]
    assert to == f"drain-{member}@example.test"
    assert subject == "Job approved"
    assert body.startswith("Job approved: Setup crew. Credit recorded.")
    # The carrier opt-out line is an SMS obligation, not an email one.
    assert "Reply STOP" not in body
    assert body.rstrip().endswith(".")  # "— GuildOS for <chapter>."
    assert body.rstrip().splitlines()[-1].startswith("— GuildOS for ")


def test_sms_row_still_goes_to_twilio(
    drain, outbox_row, delivery_mode, member_factory, cursor, fake_email, fake_twilio
):
    """Routing is per row: an sms row in the same batch is untouched by email."""
    delivery_mode("twilio")
    member = member_factory()
    cursor.execute(
        "UPDATE members SET phone = %s, sms_consent_at = now() WHERE id = %s",
        ("+15551114444", member),
    )
    outbox_row(
        event_type="ANNOUNCEMENT_SMS",
        channel="sms",
        member_id=member,
        target_table="announcement_sms_sends",
        payload={"body": "Chapter meeting moved to 8."},
    )

    assert drain()["sent"] == 1
    assert fake_email == []
    assert fake_twilio[0][0] == "+15551114444"
    assert fake_twilio[0][1].endswith("Reply STOP to opt out.")


def test_email_row_without_an_address_fails_with_no_email(
    drain, outbox_row, read_outbox, email_mode, member_factory, monkeypatch, fake_email
):
    """members.email is NOT NULL, but a blank one is reachable through an import.

    The address is stubbed rather than blanked in the table because a blank email
    is globally UNIQUE and the demo DB is shared — one test would own it forever.
    """
    email_mode("smtp")
    monkeypatch.setattr(
        "api.cron.services.outbox_drain._member_email", lambda sb, member_id: ""
    )
    member = member_factory()
    row = outbox_row(
        event_type="JOB_APPROVED", channel="email", member_id=member, payload={"title": "X"}
    )

    assert drain()["failed"] == 1
    assert read_outbox(row["id"])["last_error"] == "no_email"
    assert fake_email == []


def test_email_dry_run_simulates_without_sending(
    drain, outbox_row, read_outbox, email_mode, member_with_email, fake_email
):
    email_mode("dry_run")
    row = outbox_row(
        event_type="JOB_APPROVED",
        channel="email",
        member_id=member_with_email(),
        payload={"title": "X"},
    )

    assert drain()["simulated"] == 1
    assert read_outbox(row["id"])["status"] == "simulated"
    assert read_outbox(row["id"])["delivered_at"] is None
    assert fake_email == []


def test_email_consent_is_not_required(
    drain, outbox_row, read_outbox, email_mode, member_with_email, fake_email, cursor
):
    """A member who replied STOP to texts still gets their invoice by email."""
    email_mode("smtp")
    member = member_with_email()
    cursor.execute("UPDATE members SET sms_opted_out_at = now() WHERE id = %s", (member,))
    row = outbox_row(
        event_type="JOB_APPROVED", channel="email", member_id=member, payload={"title": "X"}
    )

    assert drain()["sent"] == 1
    assert read_outbox(row["id"])["status"] == "sent"
    assert len(fake_email) == 1


def test_unknown_email_delivery_mode_fails_loudly(
    drain, outbox_row, read_outbox, email_mode, member_with_email
):
    """A typo must not silently park every automatic message."""
    email_mode("smtpp")
    row = outbox_row(
        event_type="JOB_APPROVED",
        channel="email",
        member_id=member_with_email(),
        payload={"title": "X"},
    )

    drain()
    assert "Unknown EMAIL_DELIVERY_MODE" in read_outbox(row["id"])["last_error"]


# ── The adapter itself ───────────────────────────────────────────────────────


def test_send_email_builds_the_message_and_uses_starttls(monkeypatch):
    from api.config import settings
    from api.platform.email import send_email

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent["starttls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "ops@chapter.test")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "app-password")
    monkeypatch.setattr(settings, "EMAIL_FROM", "GuildOS <ops@chapter.test>")
    monkeypatch.setattr(settings, "EMAIL_REPLY_TO", "")

    send_email("brother@example.test", "Job approved", "Job approved: Setup crew.")

    message = sent["message"]
    assert sent["starttls"] is True
    assert sent["login"] == ("ops@chapter.test", "app-password")
    assert (sent["host"], sent["port"]) == ("smtp.gmail.com", 587)
    assert message["To"] == "brother@example.test"
    assert message["Subject"] == "Job approved"
    assert message["From"] == "GuildOS <ops@chapter.test>"
    assert message.get_content().strip() == "Job approved: Setup crew."


def test_send_email_names_the_missing_setting(monkeypatch):
    from api.config import settings
    from api.platform.email import send_email

    monkeypatch.setattr(settings, "SMTP_USER", "")
    with pytest.raises(RuntimeError, match="SMTP_USER"):
        send_email("brother@example.test", "s", "b")


# ── Migration 0159 ───────────────────────────────────────────────────────────


def test_channel_defaults_to_email_and_sms_types_are_pinned(cursor, chapter_id):
    """The backfill rule, enforced going forward by 0159's trigger."""
    import uuid

    for event_type, expected in (
        ("JOB_APPROVED", "email"),
        ("INVOICE_ISSUED", "email"),
        ("ANNOUNCEMENT_SMS", "sms"),
        ("EVENT_NOTIFY", "sms"),
    ):
        cursor.execute(
            """
            INSERT INTO message_outbox
                (chapter_id, event_type, target_table, target_id, dedup_key, payload)
            VALUES (%s, %s, 'tasks', %s, %s, '{}'::jsonb)
            RETURNING channel
            """,
            (chapter_id, event_type, str(uuid.uuid4()), f"0159:{uuid.uuid4()}"),
        )
        assert cursor.fetchone()["channel"] == expected, event_type


def test_the_new_event_types_are_accepted_by_the_check(cursor, chapter_id):
    import uuid

    for event_type in ("SETUP_CODE", "RESET_CODE", "EVENT_CREATED", "EVENT_ROLE_ASSIGNED"):
        cursor.execute(
            """
            INSERT INTO message_outbox
                (chapter_id, event_type, target_table, target_id, dedup_key, payload)
            VALUES (%s, %s, 'members', %s, %s, '{}'::jsonb)
            RETURNING channel
            """,
            (chapter_id, event_type, str(uuid.uuid4()), f"0159:{uuid.uuid4()}"),
        )
        assert cursor.fetchone()["channel"] == "email"
