"""Retry resends known failures and only closes possibly-delivered rows."""

import pytest


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_retry_after_successful_provider_and_failed_close_does_not_resend(
    sb_client, chapter_id, member_factory, outbox_row, read_outbox,
    email_mode, fake_email, delivery_mode, cursor, monkeypatch, channel,
):
    from api.announcements.services.outbox import retry_outbox_row
    from api.cron.services import outbox_drain as worker

    actor = member_factory(role="officer")
    row = outbox_row(member_id=actor, channel=channel, payload={"title": "Job"})
    email_mode("smtp")
    delivery_mode("twilio")
    cursor.execute("UPDATE members SET phone='+15551230001', sms_consent_at=now() WHERE id=%s", (actor,))
    calls = fake_email if channel == "email" else []
    if channel == "sms":
        monkeypatch.setattr(worker.twilio_client, "send_sms", lambda *args: calls.append(args) or "SM123")
    close = worker._close_row
    failed_once = False

    def fail_sent_once(*args, **kwargs):
        nonlocal failed_once
        if kwargs["status"] == "sent" and not failed_once:
            failed_once = True
            raise RuntimeError("private database error detail")
        return close(*args, **kwargs)

    monkeypatch.setattr(worker, "_close_row", fail_sent_once)
    worker.drain_outbox(sb_client, chapter_id=chapter_id)
    assert len(calls) == 1
    failed = read_outbox(row["id"])
    stamp = failed["provider_attempted_at"]
    assert stamp is not None
    assert failed["status"] == "failed"
    assert failed["last_error"] == "delivery bookkeeping failed"
    retry_outbox_row(sb_client, chapter_id=chapter_id, row_id=str(row["id"]), actor_id=actor)
    assert read_outbox(row["id"])["provider_attempted_at"] == stamp
    worker.drain_outbox(sb_client, chapter_id=chapter_id)
    assert len(calls) == 1
    delivered = read_outbox(row["id"])
    assert delivered["status"] == "sent"
    assert delivered["provider_attempted_at"] == stamp
    assert delivered["delivered_at"] is not None
    assert delivered["last_error"] is None


@pytest.mark.parametrize("channel", ["email", "sms"])
def test_retry_after_provider_failure_resends(
    sb_client, chapter_id, member_factory, outbox_row, read_outbox,
    email_mode, delivery_mode, cursor, monkeypatch, channel,
):
    from api.announcements.services.outbox import retry_outbox_row
    from api.cron.services import outbox_drain as worker

    actor = member_factory(role="officer")
    cursor.execute("UPDATE members SET phone='+15551230001', sms_consent_at=now() WHERE id=%s", (actor,))
    row = outbox_row(member_id=actor, channel=channel, payload={"title": "Job"})
    email_mode("smtp")
    delivery_mode("twilio")
    calls = []

    def provider(*args):
        calls.append(args)
        assert read_outbox(row["id"])["provider_attempted_at"] is not None
        if len(calls) == 1:
            raise RuntimeError("private provider error detail")
        return "SM123"

    if channel == "email":
        monkeypatch.setattr(worker, "send_email", provider)
    else:
        monkeypatch.setattr(worker.twilio_client, "send_sms", provider)
    worker.drain_outbox(sb_client, chapter_id=chapter_id)
    failed = read_outbox(row["id"])
    assert len(calls) == 1
    assert failed["status"] == "failed"
    assert failed["provider_attempted_at"] is None
    assert failed["delivered_at"] is None
    assert failed["last_error"] == "provider call failed"
    retry_outbox_row(sb_client, chapter_id=chapter_id, row_id=str(row["id"]), actor_id=actor)
    worker.drain_outbox(sb_client, chapter_id=chapter_id)
    assert len(calls) == 2
    delivered = read_outbox(row["id"])
    assert delivered["status"] == "sent"
    assert delivered["provider_attempted_at"] is not None
    assert delivered["delivered_at"] is not None
    assert delivered["last_error"] is None
