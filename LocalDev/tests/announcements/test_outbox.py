"""Officer outbox surface — issue #48.

GET /api/announcements/outbox (list + status filter + tenant guard + permission)
and POST /api/announcements/outbox/{id}/retry (failed -> pending, else 409).

Rows are inserted into freshly-created chapters and deleted at the end, so a
parallel run against the shared demo DB never sees them.
"""

from __future__ import annotations

import uuid

import pytest


@pytest.fixture
def chapter_factory(cursor):
    def _make() -> str:
        cursor.execute(
            """
            INSERT INTO chapters (name, organization, school)
            VALUES (%s, 'Outbox Test Org', 'Test University')
            RETURNING id
            """,
            (f"ob-test-{uuid.uuid4()}",),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def outbox_factory(cursor):
    """Insert a message_outbox row; cleans up every row it made."""
    made: list[str] = []

    def _make(
        chapter: str,
        member: str | None = None,
        *,
        status: str = "pending",
        event_type: str = "ANNOUNCEMENT_SMS",
    ) -> str:
        cursor.execute(
            """
            INSERT INTO message_outbox
                (chapter_id, event_type, member_id, target_table, target_id,
                 dedup_key, payload, status, last_error, attempts)
            VALUES (%s, %s, %s, 'announcements', gen_random_uuid(),
                    %s, %s::jsonb, %s, %s, %s)
            RETURNING id
            """,
            (
                chapter,
                event_type,
                member,
                f"ob-test-{uuid.uuid4()}",
                '{"body": "Chapter meeting at 7pm."}',
                status,
                "twilio said no" if status == "failed" else None,
                5 if status == "failed" else 0,
            ),
        )
        row_id = str(cursor.fetchone()["id"])
        made.append(row_id)
        return row_id

    yield _make
    if made:
        cursor.execute("DELETE FROM message_outbox WHERE id = ANY(%s::uuid[])", (made,))


@pytest.fixture
def officer(member_factory, give_role, set_phone):
    """Holds announcements:send (the list/retry gate)."""
    m = member_factory(role="officer")
    set_phone(m, "+15551234567")
    return m


def test_list_returns_chapter_rows_masked(officer, as_member, outbox_factory, chapter_id):
    row = outbox_factory(chapter_id, officer)
    body = as_member(officer).get("/api/announcements/outbox").json()

    entry = next(r for r in body if r["id"] == row)
    assert entry["status"] == "pending"
    assert entry["recipient_phone"] == "•••• 4567"  # never the full number
    # The footer (#57) is part of what is actually sent, so the preview shows it.
    assert entry["body"].startswith("Chapter meeting at 7pm.")
    assert entry["body"].endswith("Reply STOP to opt out.")
    assert entry["recipient_name"]


def test_list_filters_by_status(officer, as_member, outbox_factory, chapter_id):
    pending = outbox_factory(chapter_id, officer)
    failed = outbox_factory(chapter_id, officer, status="failed")

    ids = [r["id"] for r in as_member(officer).get("/api/announcements/outbox?status=failed").json()]
    assert failed in ids and pending not in ids


def test_list_is_chapter_scoped(
    officer, as_member, outbox_factory, chapter_factory, member_factory
):
    other_chapter = chapter_factory()
    foreign = outbox_factory(other_chapter, member_factory(chapter=other_chapter))

    ids = [r["id"] for r in as_member(officer).get("/api/announcements/outbox").json()]
    assert foreign not in ids


def test_treasury_rows_are_hidden_without_treasury_access(
    secretary, as_member, outbox_factory, chapter_id
):
    """Secretary holds announcements:send but no treasury:audit:view — a
    payment row names a member and an amount, so it must not be listed."""
    treasury = outbox_factory(chapter_id, secretary, event_type="PAYMENT_REJECTED")
    ordinary = outbox_factory(chapter_id, secretary)

    ids = [r["id"] for r in as_member(secretary).get("/api/announcements/outbox").json()]
    assert treasury not in ids
    assert ordinary in ids


def test_treasury_rows_show_with_treasury_access(
    officer, as_member, outbox_factory, chapter_id
):
    treasury = outbox_factory(chapter_id, officer, event_type="PAYMENT_REJECTED")
    ordinary = outbox_factory(chapter_id, officer)

    ids = [r["id"] for r in as_member(officer).get("/api/announcements/outbox").json()]
    assert treasury in ids and ordinary in ids


def test_retry_of_a_treasury_row_needs_treasury_access(
    secretary, as_member, outbox_factory, chapter_id
):
    row = outbox_factory(
        chapter_id, secretary, status="failed", event_type="PAYMENT_REJECTED"
    )
    assert as_member(secretary).post(f"/api/announcements/outbox/{row}/retry").status_code == 404


def test_plain_member_gets_403(member_factory, as_member):
    assert as_member(member_factory()).get("/api/announcements/outbox").status_code == 403


def test_retry_requeues_a_failed_row(officer, as_member, outbox_factory, chapter_id, cursor):
    row = outbox_factory(chapter_id, officer, status="failed")

    res = as_member(officer).post(f"/api/announcements/outbox/{row}/retry")
    assert res.status_code == 200, res.text

    cursor.execute(
        "SELECT status, last_error, attempts FROM message_outbox WHERE id = %s", (row,)
    )
    after = cursor.fetchone()
    assert after["status"] == "pending"
    assert after["last_error"] is None
    assert after["attempts"] == 0  # 0155 fails a row for good past 5 attempts


def test_retry_writes_an_audit_log(officer, as_member, outbox_factory, chapter_id, cursor):
    """Requeueing is an officer mutation, so it leaves an attributable trail."""
    row = outbox_factory(chapter_id, officer, status="failed")

    assert as_member(officer).post(f"/api/announcements/outbox/{row}/retry").status_code == 200

    cursor.execute(
        """
        SELECT action, actor_id, metadata FROM audit_logs
         WHERE chapter_id = %s AND target_table = 'message_outbox' AND target_id = %s
        """,
        (chapter_id, row),
    )
    entry = cursor.fetchone()
    assert entry["action"] == "OUTBOX_RETRIED"
    assert str(entry["actor_id"]) == officer
    assert entry["metadata"]["event_type"] == "ANNOUNCEMENT_SMS"


def test_retry_rejects_a_non_failed_row(officer, as_member, outbox_factory, chapter_id):
    row = outbox_factory(chapter_id, officer)  # pending
    assert as_member(officer).post(f"/api/announcements/outbox/{row}/retry").status_code == 409


def test_retry_cannot_reach_another_chapter(
    officer, as_member, outbox_factory, chapter_factory, member_factory
):
    other_chapter = chapter_factory()
    foreign = outbox_factory(
        other_chapter, member_factory(chapter=other_chapter), status="failed"
    )

    res = as_member(officer).post(f"/api/announcements/outbox/{foreign}/retry")
    assert res.status_code == 404


def test_retry_permission_gate(member_factory, as_member, outbox_factory, chapter_id):
    row = outbox_factory(chapter_id, None, status="failed")
    plain = member_factory()
    assert as_member(plain).post(f"/api/announcements/outbox/{row}/retry").status_code == 403


def test_in_app_announcement_queues_no_outbox_row(president, as_member, announcement_factory, chapter_id, cursor):
    announcement = announcement_factory(status="draft")
    response = as_member(president).post(f"/api/announcements/{announcement}/send")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "sent"
    cursor.execute(
        "SELECT count(*) AS n FROM message_outbox WHERE chapter_id=%s AND event_type='ANNOUNCEMENT_PUBLISHED'",
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 0
