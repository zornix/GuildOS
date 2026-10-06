"""The outbox drain worker (GTMLarpChecklist 2.1).

DB-backed: needs TEST_DATABASE_URL / SUPABASE_DB_URL (skipped otherwise). Covers
the rows that had no dispatcher at all before this worker existed — treasury
lifecycle events (target_table unpaid_invoices/payment_submissions/refunds) and
the plpgsql-produced job/security events (target_table tasks).

Every drain call here is scoped with `chapter_id=` so assertions stay inside the
test's own chapter; the shared demo DB accumulates pending rows from other suites
(§3.4 of the treasury harness contract).
"""

from __future__ import annotations

import uuid

import pytest

from api.cron.services.outbox_drain import drain_outbox


@pytest.fixture
def drain(sb_client, chapter_id):
    """drain_outbox scoped to this test's chapter."""

    def _drain(**kwargs):
        return drain_outbox(sb_client, chapter_id=chapter_id, **kwargs)

    return _drain


@pytest.fixture
def member_with_phone(member_factory, cursor):
    """A member the drain may actually text: phone on file AND consent (#57)."""

    def _make(phone: str = "+15551110001") -> str:
        m = member_factory()
        cursor.execute(
            "UPDATE members SET phone = %s, sms_consent_at = now() WHERE id = %s", (phone, m)
        )
        return m

    return _make


@pytest.fixture
def member_without_consent(member_factory, cursor):
    """A phone number on file and nothing else — the pre-#57 roster's state."""

    def _make(phone: str = "+15551110002") -> str:
        m = member_factory()
        cursor.execute("UPDATE members SET phone = %s WHERE id = %s", (phone, m))
        return m

    return _make


@pytest.fixture
def invoice_factory(cursor, chapter_id):
    def _make(member_id: str, *, amount_cents: int = 2500, description="Missed meeting"):
        cursor.execute(
            """
            INSERT INTO unpaid_invoices
                (chapter_id, member_id, kind, amount_cents, status, description)
            VALUES (%s, %s, 'fine', %s, 'unpaid', %s)
            RETURNING id
            """,
            (chapter_id, member_id, amount_cents, description),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def fake_twilio(monkeypatch):
    """Capture what would go to the provider instead of calling it."""
    sent: list = []
    monkeypatch.setattr(
        "api.announcements.services.twilio_client.send_sms",
        lambda to, body: sent.append((to, body)),
    )
    return sent


# ── Happy path across producers ──────────────────────────────────────────────


def test_dry_run_marks_rows_simulated_not_sent(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone, invoice_factory
):
    """The core 2.2 fix: no network call means 'simulated', never 'sent'."""
    delivery_mode("dry_run")
    member = member_with_phone()

    treasury_row = outbox_row(
        event_type="INVOICE_ISSUED",
        member_id=member,
        target_table="unpaid_invoices",
        target_id=invoice_factory(member),
    )
    task_row = outbox_row(
        event_type="JOB_REPORTED",
        member_id=member,
        target_table="tasks",
        payload={"title": "Setup crew"},
    )

    counts = drain()
    assert counts["processed"] == 2
    assert counts["simulated"] == 2
    assert counts["sent"] == 0

    for row in (treasury_row, task_row):
        after = read_outbox(row["id"])
        assert after["status"] == "simulated"
        assert after["delivered_at"] is None
        assert after["last_error"] is None


def test_drain_processes_both_treasury_and_tasks_target_tables(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone, invoice_factory
):
    """Every one of these target_tables was unreachable before the drain."""
    member = member_with_phone()
    rows = [
        outbox_row(
            event_type="INVOICE_ISSUED",
            member_id=member,
            target_table="unpaid_invoices",
            target_id=invoice_factory(member),
        ),
        outbox_row(
            event_type="JOB_APPROVED",
            member_id=member,
            target_table="tasks",
            payload={"title": "Setup crew"},
        ),
        outbox_row(
            event_type="SECURITY_ASSIGNED",
            member_id=member,
            target_table="tasks",
            payload={"title": "Security shift", "event_date": "2026-09-01"},
        ),
        outbox_row(
            event_type="SECURITY_SWAP_REQUESTED",
            member_id=member,
            target_table="security_swap_requests",
            payload={"note": "family emergency"},
        ),
    ]

    assert drain()["processed"] == len(rows)
    for row in rows:
        assert read_outbox(row["id"])["status"] == "simulated"


def test_terminal_rows_are_not_reprocessed(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone
):
    row = outbox_row(
        event_type="JOB_APPROVED", member_id=member_with_phone(), payload={"title": "Job"}
    )
    drain()
    first = read_outbox(row["id"])
    assert drain()["processed"] == 0  # nothing left pending
    second = read_outbox(row["id"])

    assert first["status"] == second["status"] == "simulated"
    assert first["attempts"] == second["attempts"] == 1


# ── attempts / last_error bookkeeping ────────────────────────────────────────


def test_attempts_increments_from_zero(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone
):
    row = outbox_row(
        event_type="JOB_APPROVED", member_id=member_with_phone(), payload={"title": "Job"}
    )
    assert row["attempts"] == 0

    drain()
    assert read_outbox(row["id"])["attempts"] == 1


def test_template_failure_fails_one_row_without_killing_the_batch(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone
):
    """An unrenderable row is closed out with a reason; its neighbours still go."""
    member = member_with_phone()
    # ANNOUNCEMENT_SMS passes the sender's body through — with no body there is
    # nothing to send, which is exactly the "template cannot render" path.
    bad = outbox_row(
        event_type="ANNOUNCEMENT_SMS",
        member_id=member,
        target_table="announcement_sms_sends",
        payload={},
    )
    good = outbox_row(
        event_type="JOB_APPROVED", member_id=member, payload={"title": "Setup crew"}
    )

    counts = drain()
    assert counts["failed"] == 1
    assert counts["simulated"] == 1

    failed = read_outbox(bad["id"])
    assert failed["status"] == "failed"
    assert "body" in failed["last_error"]
    assert failed["attempts"] == 1
    assert read_outbox(good["id"])["status"] == "simulated"


def test_row_without_a_member_is_failed_with_a_reason(
    drain, delivery_mode, outbox_row, read_outbox
):
    """Legacy recipient-less rows still fail safely with a clear reason."""
    row = outbox_row(
        event_type="ANNOUNCEMENT_PUBLISHED",
        member_id=None,
        target_table="announcements",
        payload={"title": "Chapter meeting moved"},
    )
    drain()

    after = read_outbox(row["id"])
    assert after["status"] == "failed"
    assert after["last_error"] == "no recipient"


# ── twilio mode ──────────────────────────────────────────────────────────────


def test_twilio_mode_without_a_phone_fails_with_no_phone(
    drain, delivery_mode, outbox_row, read_outbox, member_factory, fake_twilio
):
    delivery_mode("twilio")
    row = outbox_row(
        event_type="JOB_APPROVED",
        member_id=member_factory(),  # no phone set
        payload={"title": "Setup crew"},
    )
    drain()

    after = read_outbox(row["id"])
    assert after["status"] == "failed"
    assert after["last_error"] == "no phone"
    assert fake_twilio == []  # nothing was attempted


def test_twilio_mode_sends_and_records_delivered_at(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone, fake_twilio
):
    delivery_mode("twilio")
    row = outbox_row(
        event_type="JOB_APPROVED",
        member_id=member_with_phone("+15551119999"),
        payload={"title": "Setup crew"},
    )
    drain()

    after = read_outbox(row["id"])
    assert after["status"] == "sent"
    assert after["delivered_at"] is not None
    assert len(fake_twilio) == 1
    to, body = fake_twilio[0]
    assert to == "+15551119999"
    assert body.startswith("Job approved: Setup crew. Credit recorded.")


def test_provider_error_fails_the_row_with_the_error_recorded(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone, monkeypatch
):
    delivery_mode("twilio")

    def _boom(to, body):
        raise RuntimeError("twilio 401 unauthorized")

    monkeypatch.setattr("api.announcements.services.twilio_client.send_sms", _boom)

    row = outbox_row(
        event_type="JOB_APPROVED",
        member_id=member_with_phone(),
        payload={"title": "Setup crew"},
    )
    drain()

    after = read_outbox(row["id"])
    assert after["status"] == "failed"
    assert "twilio 401 unauthorized" in after["last_error"]


def test_unknown_delivery_mode_fails_only_the_sms_rows(
    drain,
    delivery_mode,
    email_mode,
    outbox_row,
    read_outbox,
    member_with_phone,
    member_factory,
    fake_email,
):
    """A typo must not silently park a message — but MESSAGE_DELIVERY_MODE is
    the SMS knob, so it must not take the email rows down with it either."""
    delivery_mode("twilllio")
    email_mode("smtp")

    sms = outbox_row(
        event_type="JOB_APPROVED", member_id=member_with_phone(), payload={"title": "X"}
    )
    email = outbox_row(
        event_type="JOB_APPROVED",
        channel="email",
        member_id=member_factory(),
        payload={"title": "X"},
    )

    drain()

    assert read_outbox(sms["id"])["status"] == "failed"
    assert "Unknown MESSAGE_DELIVERY_MODE" in read_outbox(sms["id"])["last_error"]
    assert read_outbox(email["id"])["status"] == "sent"
    assert len(fake_email) == 1


# ── Payload enrichment (producers write ids, not amounts) ────────────────────


def test_invoice_amount_is_read_from_the_target_row(
    drain, delivery_mode, outbox_row, member_with_phone, invoice_factory, fake_twilio
):
    """treasury/notifications.py enqueues identifiers only; the drain enriches."""
    delivery_mode("twilio")
    member = member_with_phone("+15551112222")
    invoice = invoice_factory(member, amount_cents=4200, description="Late dues")
    outbox_row(
        event_type="INVOICE_ISSUED",
        member_id=member,
        target_table="unpaid_invoices",
        target_id=invoice,
        payload={"event_type": "INVOICE_ISSUED", "member_id": member},
    )

    drain()
    assert [body.split("\n")[0] for _, body in fake_twilio] == [
        "New charge: $42.00 — Late dues. Log in to view."
    ]


def test_dangling_target_row_still_delivers_a_neutral_message(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone
):
    """A missing target row degrades the copy; it never fails the row."""
    row = outbox_row(
        event_type="INVOICE_ISSUED",
        member_id=member_with_phone(),
        target_table="unpaid_invoices",
        target_id=str(uuid.uuid4()),
    )
    drain()
    assert read_outbox(row["id"])["status"] == "simulated"


# ── Batch limit / ordering ───────────────────────────────────────────────────


def test_batch_limit_takes_the_oldest_row_first(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone
):
    member = member_with_phone()
    rows = [
        outbox_row(event_type="JOB_APPROVED", member_id=member, payload={"title": f"J{i}"})
        for i in range(3)
    ]
    assert drain(limit=1)["processed"] == 1
    assert read_outbox(rows[0]["id"])["status"] == "simulated"
    assert read_outbox(rows[2]["id"])["status"] == "pending"


# ── PAYMENT_REMINDER: the reminder endpoint's queue ──────────────────────────


def test_payment_reminder_dedups_within_the_same_day(
    sb_client, cursor, chapter_id, member_with_phone
):
    from api.treasury.notifications import enqueue_payment_reminder

    member = member_with_phone()
    kwargs = dict(
        chapter_id=chapter_id,
        member_id=member,
        unpaid_count=2,
        unpaid_total_cents=5000,
        sb=sb_client,
    )
    first = enqueue_payment_reminder(**kwargs)
    second = enqueue_payment_reminder(**kwargs)

    assert first is not None
    assert second is None  # today's reminder was already queued

    cursor.execute(
        """
        SELECT count(*) AS n FROM message_outbox
        WHERE chapter_id = %s AND event_type = 'PAYMENT_REMINDER'
        """,
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 1


def test_payment_reminder_can_be_resent_on_a_later_day(
    sb_client, cursor, chapter_id, member_with_phone
):
    from datetime import date, timedelta

    from api.treasury.notifications import enqueue_payment_reminder

    member = member_with_phone()
    today = date.today()
    base = dict(
        chapter_id=chapter_id,
        member_id=member,
        unpaid_count=1,
        unpaid_total_cents=2500,
        sb=sb_client,
    )
    assert enqueue_payment_reminder(on_date=today, **base)
    assert enqueue_payment_reminder(on_date=today + timedelta(days=1), **base)

    cursor.execute(
        """
        SELECT count(*) AS n FROM message_outbox
        WHERE chapter_id = %s AND event_type = 'PAYMENT_REMINDER'
        """,
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 2


def test_payment_reminder_renders_the_owed_total(
    drain, sb_client, cursor, email_mode, chapter_id, member_factory, fake_email
):
    """Treasury reminders are email now (ADR-0005), not SMS."""
    from api.treasury.notifications import enqueue_payment_reminder

    member = member_factory()
    cursor.execute(
        "UPDATE members SET email = %s WHERE id = %s",
        (f"reminder-{member}@example.test", member),
    )
    email_mode("smtp")
    enqueue_payment_reminder(
        chapter_id=chapter_id,
        member_id=member,
        unpaid_count=3,
        unpaid_total_cents=7500,
        sb=sb_client,
    )
    drain()

    assert [body.split("\n")[0] for _, _, body in fake_email] == [
        "Reminder: 3 unpaid charges totaling $75.00. Log in to pay."
    ]


# ── HTTP surface ─────────────────────────────────────────────────────────────


def test_drain_route_returns_counts(cron_client, auth_header, outbox_row, member_with_phone):
    outbox_row(
        event_type="JOB_APPROVED",
        member_id=member_with_phone(),
        payload={"title": "Setup crew"},
    )
    resp = cron_client.get("/api/cron/drain-outbox", headers=auth_header())
    assert resp.status_code == 200
    counts = resp.json()
    assert set(counts) == {"processed", "sent", "simulated", "failed"}
    assert counts["simulated"] >= 1


# ── Claiming (issue #32) ─────────────────────────────────────────────────────


@pytest.fixture
def claim(sb_client, chapter_id):
    """outbox_claim_batch scoped to this test's chapter."""
    from api.platform.rpc import call_rpc

    def _claim(client=None, *, limit: int = 10) -> list:
        return (
            call_rpc(
                "outbox_claim_batch",
                {"p_limit": limit, "p_chapter_id": chapter_id},
                sb=client or sb_client,
            ).data
            or []
        )

    return _claim


def test_a_claimed_row_is_not_handed_to_a_second_worker(claim, db_url, outbox_row):
    """The duplicate-SMS bug: two overlapping drains must not share a row."""
    from api.platform.postgres import PostgresClient

    row = outbox_row(event_type="JOB_APPROVED", payload={"title": "Setup crew"})

    other_worker = PostgresClient(db_url)
    try:
        first = claim()
        second = claim(other_worker)
    finally:
        other_worker.close()

    assert [r["id"] for r in first] == [row["id"]]
    assert [r["status"] for r in first] == ["sending"]
    assert second == []


def test_an_abandoned_claim_is_requeued_and_reclaimed(claim, cursor, outbox_row, read_outbox):
    """A worker that died holding a row must not strand it forever."""
    stale = outbox_row(event_type="JOB_APPROVED", status="sending", payload={"title": "Old"})
    fresh = outbox_row(event_type="JOB_APPROVED", status="sending", payload={"title": "New"})
    cursor.execute(
        "UPDATE message_outbox SET claimed_at = now() - interval '16 minutes' WHERE id = %s",
        (stale["id"],),
    )
    cursor.execute(
        "UPDATE message_outbox SET claimed_at = now() WHERE id = %s", (fresh["id"],)
    )

    claimed = claim()

    assert [r["id"] for r in claimed] == [stale["id"]]  # the fresh claim is still owned
    assert read_outbox(stale["id"])["attempts"] == 1
    assert read_outbox(fresh["id"])["status"] == "sending"


def test_a_row_past_the_attempt_cap_is_failed_instead_of_claimed(
    claim, cursor, outbox_row, read_outbox
):
    """With a reaper in place, a row that keeps killing the worker needs a floor."""
    row = outbox_row(event_type="JOB_APPROVED", payload={"title": "Poison"})
    cursor.execute("UPDATE message_outbox SET attempts = 5 WHERE id = %s", (row["id"],))

    assert claim() == []

    after = read_outbox(row["id"])
    assert after["status"] == "failed"
    assert "attempt cap" in after["last_error"]


# ── Consent (#57) ────────────────────────────────────────────────────────────


def test_twilio_mode_refuses_a_member_without_consent(
    drain, delivery_mode, outbox_row, read_outbox, member_without_consent, fake_twilio
):
    """A phone number is not permission to text it (#57)."""
    delivery_mode("twilio")
    row = outbox_row(
        event_type="JOB_APPROVED",
        member_id=member_without_consent(),
        payload={"title": "Setup crew"},
    )

    assert drain()["failed"] == 1

    after = read_outbox(row["id"])
    assert after["status"] == "failed"
    assert after["last_error"] == "no_consent"
    assert fake_twilio == []


def test_twilio_mode_refuses_a_member_who_replied_stop(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone, cursor, fake_twilio
):
    member = member_with_phone()
    cursor.execute("UPDATE members SET sms_opted_out_at = now() WHERE id = %s", (member,))
    delivery_mode("twilio")
    row = outbox_row(event_type="JOB_APPROVED", member_id=member, payload={"title": "Setup"})

    drain()

    assert read_outbox(row["id"])["last_error"] == "no_consent"
    assert fake_twilio == []


def test_a_consenting_member_is_sent_a_body_with_the_opt_out_footer(
    drain, delivery_mode, outbox_row, read_outbox, member_with_phone, fake_twilio
):
    delivery_mode("twilio")
    row = outbox_row(
        event_type="JOB_APPROVED", member_id=member_with_phone(), payload={"title": "Setup"}
    )

    assert drain()["sent"] == 1

    assert read_outbox(row["id"])["status"] == "sent"
    assert len(fake_twilio) == 1
    assert fake_twilio[0][1].endswith("Reply STOP to opt out.")


def test_dry_run_still_simulates_a_member_without_consent(
    drain, delivery_mode, outbox_row, read_outbox, member_without_consent, fake_twilio
):
    """Consent gates real sends only — local dev must still show the message."""
    delivery_mode("dry_run")
    row = outbox_row(
        event_type="JOB_APPROVED", member_id=member_without_consent(), payload={"title": "X"}
    )

    assert drain()["simulated"] == 1

    assert read_outbox(row["id"])["status"] == "simulated"
    assert fake_twilio == []


def test_provider_call_is_stamped_first(drain, delivery_mode, outbox_row, read_outbox, member_with_phone, monkeypatch):
    delivery_mode("twilio")
    row = outbox_row(event_type="JOB_APPROVED", member_id=member_with_phone(), payload={"title": "Job"})
    stamps = []

    def provider(*args):
        stamps.append(read_outbox(row["id"]).get("provider_attempted_at"))
        return "SM123"

    monkeypatch.setattr("api.announcements.services.twilio_client.send_sms", provider)
    drain()
    assert len(stamps) == 1 and stamps[0] is not None


def test_unknown_outcome_is_parked_not_resent(drain, delivery_mode, outbox_row, read_outbox, member_with_phone, monkeypatch, cursor):
    from api.cron.services import outbox_drain as worker

    delivery_mode("twilio")
    row = outbox_row(event_type="JOB_APPROVED", member_id=member_with_phone(), payload={"title": "Job"})
    calls = []
    monkeypatch.setattr(worker.twilio_client, "send_sms", lambda *args: calls.append(args))

    def failed_close(*args, **kwargs):
        raise RuntimeError("bookkeeping unavailable")

    with monkeypatch.context() as failure:
        failure.setattr(worker, "_close_row", failed_close)
        drain()
    assert read_outbox(row["id"])["status"] == "sending"
    cursor.execute("UPDATE message_outbox SET claimed_at=now()-interval '20 minutes' WHERE id=%s", (row["id"],))
    drain()
    assert len(calls) == 1
    after = read_outbox(row["id"])
    assert after["status"] == "failed"
    assert after["last_error"].startswith("delivery outcome unknown")


def test_claimed_but_never_attempted_is_requeued_with_its_attempt_back(claim, cursor, outbox_row, read_outbox):
    row = outbox_row(status="sending")
    cursor.execute("UPDATE message_outbox SET claimed_at=now()-interval '20 minutes', attempts=1 WHERE id=%s", (row["id"],))
    claim(limit=0)
    after = read_outbox(row["id"])
    assert after["status"] == "pending"
    assert after["attempts"] == 0


def test_twilio_sid_is_recorded(drain, delivery_mode, outbox_row, read_outbox, member_with_phone, monkeypatch):
    delivery_mode("twilio")
    row = outbox_row(event_type="JOB_APPROVED", member_id=member_with_phone(), payload={"title": "Job"})
    monkeypatch.setattr("api.announcements.services.twilio_client.send_sms", lambda *args: "SM123")
    drain()
    assert read_outbox(row["id"]).get("provider_message_id") == "SM123"


def test_dry_run_never_stamps(drain, delivery_mode, outbox_row, read_outbox, member_with_phone):
    row = outbox_row(event_type="JOB_APPROVED", member_id=member_with_phone(), payload={"title": "Job"})
    drain()
    after = read_outbox(row["id"])
    assert "provider_attempted_at" in after
    assert after["provider_attempted_at"] is None
    assert after["status"] == "simulated"


def test_drain_stops_when_the_budget_is_spent(drain, outbox_row, read_outbox, monkeypatch):
    from api.cron.services import outbox_drain as worker

    row = outbox_row()
    monkeypatch.setattr(worker, "DRAIN_BUDGET_SECONDS", 0, raising=False)
    assert drain()["processed"] == 0
    after = read_outbox(row["id"])
    assert after["status"] == "pending"
    assert after["attempts"] == 0


def test_budget_expiring_mid_batch_leaves_unused_claims_refundable(
    drain, claim, outbox_row, read_outbox, member_with_phone, cursor, monkeypatch
):
    from types import SimpleNamespace
    from api.cron.services import outbox_drain as worker

    member = member_with_phone()
    rows = [outbox_row(event_type="JOB_APPROVED", member_id=member, payload={"title": "Job"}) for _ in range(26)]
    clock = [0]
    monkeypatch.setattr(worker, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    deliver = worker._deliver_row

    def slow_delivery(*args, **kwargs):
        status = deliver(*args, **kwargs)
        clock[0] = worker.DRAIN_BUDGET_SECONDS + 1
        return status

    monkeypatch.setattr(worker, "_deliver_row", slow_delivery)
    assert drain()["processed"] == 1
    assert read_outbox(rows[0]["id"])["status"] == "simulated"
    unclaimed = read_outbox(rows[-1]["id"])
    assert unclaimed["status"] == "pending"
    assert unclaimed["attempts"] == 0
    unused = read_outbox(rows[1]["id"])
    assert unused["status"] == "sending"
    assert unused["provider_attempted_at"] is None
    cursor.execute(
        "UPDATE message_outbox SET claimed_at=now()-interval '20 minutes' WHERE chapter_id=%s AND status='sending'",
        (unused["chapter_id"],),
    )
    claim(limit=0)
    unused = read_outbox(rows[1]["id"])
    assert unused["status"] == "pending"
    assert unused["attempts"] == 0


@pytest.mark.parametrize("target_table", ["announcement_sms_sends", "event_notification_sends"])
@pytest.mark.parametrize("remaining_status", [None, "failed", "pending", "sending"])
def test_retry_reconciles_parent_only_after_all_children_finish(
    target_table, remaining_status, cursor, chapter_id, member_factory,
    outbox_row, sb_client, delivery_mode
):
    from api.announcements.services.outbox import retry_outbox_row
    actor = member_factory(role="officer")
    if target_table == "announcement_sms_sends":
        cursor.execute("INSERT INTO announcements (chapter_id,title,body,audience,status) VALUES (%s,'Update','Body','chapter','draft') RETURNING id", (chapter_id,))
        parent_column = "announcement_id"
    else:
        cursor.execute("INSERT INTO events (chapter_id,title,date,time,location) VALUES (%s,'Event',CURRENT_DATE,'19:00','Hall') RETURNING id", (chapter_id,))
        parent_column = "event_id"
    target = str(cursor.fetchone()["id"])
    cursor.execute(f"INSERT INTO {target_table} (chapter_id,{parent_column},sender_id,recipient_count,recipient_member_ids,body_snapshot,delivery_mode,status) VALUES (%s,%s,%s,1,'[]','Body','dry_run','failed') RETURNING id", (chapter_id,target,actor))
    parent = str(cursor.fetchone()["id"])
    row = outbox_row(event_type="ANNOUNCEMENT_SMS" if target_table == "announcement_sms_sends" else "EVENT_NOTIFY", member_id=actor, target_table=target_table, target_id=parent, payload={"body":"Body"}, status="failed")
    if remaining_status:
        outbox_row(member_id=actor, target_table=target_table, target_id=parent, status=remaining_status)
    retry_outbox_row(sb_client, chapter_id=chapter_id, row_id=str(row["id"]), actor_id=actor)
    assert drain_outbox(sb_client, chapter_id=chapter_id, limit=1)["simulated"] == 1
    cursor.execute(f"SELECT status FROM {target_table} WHERE id=%s AND chapter_id=%s", (parent, chapter_id))
    assert cursor.fetchone()["status"] == ("failed" if remaining_status else "sent")


def test_parent_reconcile_failure_keeps_the_delivered_row(
    cursor, chapter_id, member_factory, outbox_row, sb_client, delivery_mode, monkeypatch
):
    """A sent message must never be re-marked failed (and so retried) over parent bookkeeping."""
    actor = member_factory(role="officer")
    cursor.execute("INSERT INTO announcements (chapter_id,title,body,audience,status) VALUES (%s,'Update','Body','chapter','draft') RETURNING id", (chapter_id,))
    target = str(cursor.fetchone()["id"])
    cursor.execute("INSERT INTO announcement_sms_sends (chapter_id,announcement_id,sender_id,recipient_count,recipient_member_ids,body_snapshot,delivery_mode,status) VALUES (%s,%s,%s,1,'[]','Body','dry_run','failed') RETURNING id", (chapter_id, target, actor))
    parent = str(cursor.fetchone()["id"])
    row = outbox_row(event_type="ANNOUNCEMENT_SMS", member_id=actor, target_table="announcement_sms_sends", target_id=parent, payload={"body": "Body"}, status="pending")
    real_table = sb_client.table

    def table(name):
        if name == "announcement_sms_sends":
            raise RuntimeError("parent write unavailable")
        return real_table(name)

    monkeypatch.setattr(sb_client, "table", table)
    assert drain_outbox(sb_client, chapter_id=chapter_id, limit=1)["simulated"] == 1
    cursor.execute("SELECT status FROM message_outbox WHERE id=%s", (row["id"],))
    assert cursor.fetchone()["status"] == "simulated"
