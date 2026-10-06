"""Announcement SMS send — confirmation step, RPC effects, dispatch, send log.

Runs entirely in settings.MESSAGE_DELIVERY_MODE=dry_run: nothing leaves the
process, and the outbox rows say so ('simulated', not 'sent').
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest


def _send(client, ann_id, count, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        f"/api/announcements/{ann_id}/send-sms",
        json={"confirmed_recipient_count": count},
        headers=headers,
    )


# ── Recipient resolution / preview ───────────────────────────────────────────


def test_preview_excludes_members_without_phone(
    president, as_member, member_factory, set_phone, announcement_factory
):
    a = member_factory()
    b = member_factory()
    set_phone(a, "+15551230001")
    set_phone(b, "+15551230002")
    member_factory()  # phone NULL
    member_factory()  # phone NULL — members_phone_e164 forbids storing blanks

    ann = announcement_factory(audience="chapter")
    resp = as_member(president).get(f"/api/announcements/{ann}/sms-preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recipient_count"] == 3  # president + a + b
    assert body["no_phone_count"] == 2


def test_twilio_preview_counts_only_consented_members(
    president, as_member, member_factory, set_phone, announcement_factory,
    delivery_mode, cursor
):
    """The confirmed count must match what will actually send (#57).

    In twilio mode an unconsented member is dropped by the delivery path, so
    counting them in the preview promised the officer a blast that never happened.
    `no_phone_count` still means exactly that — no phone, not "no consent".
    """
    consented = member_factory()
    set_phone(consented, "+15551250001")
    cursor.execute("UPDATE members SET sms_consent_at = now() WHERE id = %s", (consented,))
    unconsented = member_factory()
    set_phone(unconsented, "+15551250002")
    member_factory()  # phone NULL

    ann = announcement_factory(audience="chapter")
    client = as_member(president)

    # dry_run simulates everyone, so the president (no consent) still counts.
    assert client.get(f"/api/announcements/{ann}/sms-preview").json()["recipient_count"] == 3

    delivery_mode("twilio")
    body = client.get(f"/api/announcements/{ann}/sms-preview").json()
    assert body["recipient_count"] == 1  # only the consented member
    assert body["no_phone_count"] == 1
    # The dropped member is counted somewhere, not silently missing (#89).
    assert body["no_consent_count"] == 2  # the unconsented member + the president


def test_preview_officers_audience(
    president, as_member, member_factory, give_role, set_phone, announcement_factory
):
    # 0147 backfilled every active members.role='officer' account into
    # member_roles, and the audience now resolves from member_roles only.
    legacy_officer = member_factory(role="officer")
    give_role(legacy_officer, "officer")
    set_phone(legacy_officer, "+15551240001")
    chair = member_factory()
    give_role(chair, "social_chair")
    set_phone(chair, "+15551240002")
    plain = member_factory()
    set_phone(plain, "+15551240003")

    ann = announcement_factory(audience="officers")
    resp = as_member(president).get(f"/api/announcements/{ann}/sms-preview")
    assert resp.status_code == 200
    # president (rbac role) + legacy officer + chair; the plain member is excluded
    assert resp.json()["recipient_count"] == 3


def test_preview_members_with_balance_audience(
    cursor, chapter_id, president, as_member, member_factory, set_phone, announcement_factory
):
    owing_with_phone = member_factory()
    set_phone(owing_with_phone, "+15551250001")
    owing_no_phone = member_factory()
    settled = member_factory()
    set_phone(settled, "+15551250002")

    # Audiences read live balances, so the debt is an invoice, not a cache row.
    for member, cents in ((owing_with_phone, 2500), (owing_no_phone, 1000)):
        cursor.execute(
            """
            INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
            VALUES (%s, %s, 'fine', %s, 'unpaid')
            """,
            (chapter_id, member, cents),
        )

    ann = announcement_factory(audience="members_with_balance")
    resp = as_member(president).get(f"/api/announcements/{ann}/sms-preview")
    assert resp.status_code == 200
    assert resp.json() == {
        "announcement_id": ann,
        "audience": "members_with_balance",
        "recipient_count": 1,
        "no_phone_count": 1,
        "no_consent_count": 0,  # dry_run reaches everyone with a phone
    }


def test_preview_unknown_announcement_is_404(president, as_member):
    resp = as_member(president).get(f"/api/announcements/{uuid.uuid4()}/sms-preview")
    assert resp.status_code == 404


# ── Two-phase confirm ────────────────────────────────────────────────────────


def test_count_mismatch_returns_409_with_fresh_count(
    president, as_member, member_factory, set_phone, announcement_factory
):
    extra = member_factory()
    set_phone(extra, "+15551260001")
    ann = announcement_factory()
    client = as_member(president)

    resp = _send(client, ann, count=99)  # stale confirmation
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["recipient_count"] == 2  # president + extra: the fresh count


def test_draft_announcement_is_422(president, as_member, announcement_factory):
    ann = announcement_factory(status="draft")
    resp = _send(as_member(president), ann, count=1)
    assert resp.status_code == 422


def test_unknown_announcement_send_is_404(president, as_member):
    resp = _send(as_member(president), str(uuid.uuid4()), count=1)
    assert resp.status_code == 404


# ── Send effects ─────────────────────────────────────────────────────────────


def test_send_writes_log_outbox_and_audit(
    cursor, chapter_id, president, as_member, member_factory, set_phone, announcement_factory
):
    a = member_factory()
    set_phone(a, "+15551270001")
    member_factory()  # no phone — excluded
    ann = announcement_factory(body="Dues due Friday.")
    client = as_member(president)

    resp = _send(client, ann, count=2)
    assert resp.status_code == 200, resp.text
    send = resp.json()
    assert send["recipient_count"] == 2
    assert send["sender_id"] == president

    cursor.execute(
        "SELECT * FROM announcement_sms_sends WHERE chapter_id = %s", (chapter_id,)
    )
    rows = cursor.fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert str(row["announcement_id"]) == ann
    assert str(row["sender_id"]) == president
    assert row["recipient_count"] == 2
    assert row["body_snapshot"] == "Dues due Friday."
    assert row["status"] == "sent"  # dry_run dispatch marked it sent

    cursor.execute(
        """
        SELECT * FROM message_outbox
        WHERE chapter_id = %s AND event_type = 'ANNOUNCEMENT_SMS'
        """,
        (chapter_id,),
    )
    outbox = cursor.fetchall()
    assert len(outbox) == 2
    assert {str(r["member_id"]) for r in outbox} == {president, a}
    # dry_run made no network call, so the rows say 'simulated' — never 'sent'.
    assert all(r["status"] == "simulated" for r in outbox)
    assert all(r["delivery_mode"] == "sms" for r in outbox)

    cursor.execute(
        """
        SELECT * FROM audit_logs
        WHERE chapter_id = %s AND target_table = 'announcement_sms_sends'
        """,
        (chapter_id,),
    )
    audits = cursor.fetchall()
    assert len(audits) == 1
    assert str(audits[0]["actor_id"]) == president
    assert str(audits[0]["target_id"]) == send["id"]


def test_resend_with_same_idempotency_key_does_not_duplicate(
    cursor, chapter_id, president, as_member, member_factory, set_phone, announcement_factory
):
    a = member_factory()
    set_phone(a, "+15551280001")
    ann = announcement_factory()
    client = as_member(president)

    first = _send(client, ann, count=2, key="sms-blast-1")
    second = _send(client, ann, count=2, key="sms-blast-1")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    cursor.execute(
        "SELECT count(*) AS n FROM announcement_sms_sends WHERE chapter_id = %s",
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 1
    cursor.execute(
        """
        SELECT count(*) AS n FROM message_outbox
        WHERE chapter_id = %s AND event_type = 'ANNOUNCEMENT_SMS'
        """,
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 2  # one per recipient, no duplicates


# ── Send log (exec visibility) ───────────────────────────────────────────────


def test_sms_log_lists_send_with_sender(
    president, as_member, member_factory, set_phone, announcement_factory
):
    a = member_factory()
    set_phone(a, "+15551290001")
    ann = announcement_factory(title="Formal tickets")
    client = as_member(president)
    send_id = _send(client, ann, count=2).json()["id"]

    resp = client.get("/api/announcements/sms-log", params={"limit": 10})
    assert resp.status_code == 200
    log = resp.json()
    assert len(log) == 1
    entry = log[0]
    assert entry["id"] == send_id
    assert entry["sender_id"] == president
    assert entry["recipient_count"] == 2
    assert entry["status"] == "sent"
    assert entry["announcement_title"] == "Formal tickets"
    assert "created_at" in entry


# ── Consent (#57) ────────────────────────────────────────────────────────────


@pytest.fixture
def fake_twilio(monkeypatch):
    """Capture what would go to the provider instead of calling it."""
    sent: list = []
    monkeypatch.setattr(
        "api.announcements.services.twilio_client.send_sms",
        lambda to, body: sent.append((to, body)),
    )
    return sent


def test_twilio_dispatch_refuses_a_member_without_consent(
    cursor, chapter_id, sb_client, member_factory, set_phone, fake_twilio
):
    """The second enforcement path: a queued row whose member never consented (#57).

    The preview already drops them, so this only fires when consent lapsed
    between the queue and the dispatch — exactly when it must still hold.
    """
    from api.announcements.services import sms as sms_svc

    member = member_factory()
    set_phone(member, "+15551310001")  # phone on file, no sms_consent_at
    cursor.execute(
        """
        INSERT INTO message_outbox
            (chapter_id, event_type, member_id, target_table, target_id, dedup_key,
             payload, status, delivery_mode, channel)
        VALUES (%s, 'ANNOUNCEMENT_SMS', %s, 'announcement_sms_sends',
                gen_random_uuid(), gen_random_uuid()::text,
                '{"body": "Dues due Friday."}'::jsonb, 'pending', 'twilio', 'sms')
        RETURNING *
        """,
        (chapter_id, member),
    )
    row = dict(cursor.fetchone())

    assert sms_svc._dispatch_twilio_row(sb_client, row, chapter_name="Test") == "failed"

    cursor.execute("SELECT * FROM message_outbox WHERE id = %s", (row["id"],))
    after = cursor.fetchone()
    assert after["status"] == "failed"
    assert after["last_error"] == "no_consent"
    assert fake_twilio == []


# ── Append-only guarantees ───────────────────────────────────────────────────


def test_sms_send_rows_are_append_only(
    cursor, chapter_id, president, as_member, announcement_factory
):
    ann = announcement_factory()
    send_id = _send(as_member(president), ann, count=1).json()["id"]

    with pytest.raises(psycopg2.DatabaseError, match="append-only"):
        cursor.execute(
            "UPDATE announcement_sms_sends SET body_snapshot = 'tampered' WHERE id = %s",
            (send_id,),
        )
    with pytest.raises(psycopg2.DatabaseError, match="forbidden"):
        cursor.execute("DELETE FROM announcement_sms_sends WHERE id = %s", (send_id,))
