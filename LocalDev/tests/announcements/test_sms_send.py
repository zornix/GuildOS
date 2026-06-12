"""Announcement SMS send — confirmation step, RPC effects, dispatch, send log.

Runs entirely in MESSAGE_DELIVERY_MODE=dry_run: nothing leaves the process.
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
    blank = member_factory()
    set_phone(blank, "   ")  # whitespace-only counts as no phone

    ann = announcement_factory(audience="chapter")
    resp = as_member(president).get(f"/api/announcements/{ann}/sms-preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["recipient_count"] == 3  # president + a + b
    assert body["no_phone_count"] == 2


def test_preview_officers_audience(
    president, as_member, member_factory, give_role, set_phone, announcement_factory
):
    legacy_officer = member_factory(role="officer")
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

    for member, cents in ((owing_with_phone, 2500), (owing_no_phone, 1000), (settled, 0)):
        cursor.execute(
            """
            INSERT INTO member_finance_accounts
                (chapter_id, member_id, total_owed_cents, outstanding_balance_cents)
            VALUES (%s, %s, %s, %s)
            """,
            (chapter_id, member, cents, cents),
        )

    ann = announcement_factory(audience="members_with_balance")
    resp = as_member(president).get(f"/api/announcements/{ann}/sms-preview")
    assert resp.status_code == 200
    assert resp.json() == {
        "announcement_id": ann,
        "audience": "members_with_balance",
        "recipient_count": 1,
        "no_phone_count": 1,
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
    assert all(r["status"] == "sent" for r in outbox)  # dry_run: marked sent, no network
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
