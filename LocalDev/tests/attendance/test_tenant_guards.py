"""Tenant guards for the attendance surface (imp-tenant-guards.md Verification).

Superuser connection (bypasses RLS); exercises the at_* RPCs and the D2 derive
trigger directly. Every assertion is scoped to freshly-inserted chapters.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from tests.attendance.conftest import set_attendance, review_excuse


# ── cross-chapter isolation ───────────────────────────────────────────────────

def test_foreign_chapter_cannot_set_attendance(
    cursor, chapter_factory, event_factory, member_factory
):
    chapter_a = chapter_factory()
    chapter_b = chapter_factory()
    event_a = event_factory(chapter_a)
    member_a = member_factory(chapter=chapter_a)
    officer_b = member_factory(chapter=chapter_b)

    # Officer of B (whose JWT can only ever supply chapter_id=B) aimed at A's event.
    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        set_attendance(cursor, chapter_b, event_a, member_a, "present", officer_b)
    assert "not found in chapter" in str(exc.value)


def test_foreign_chapter_cannot_review_excuse(
    cursor, chapter_factory, event_factory, member_factory, excuse_factory
):
    chapter_a = chapter_factory()
    chapter_b = chapter_factory()
    event_a = event_factory(chapter_a)
    member_a = member_factory(chapter=chapter_a)
    officer_b = member_factory(chapter=chapter_b)
    excuse_a = excuse_factory(chapter_a, event_a, member_a)

    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        review_excuse(cursor, chapter_b, excuse_a, "approved", officer_b)
    assert "excuse" in str(exc.value) and "not found in chapter" in str(exc.value)


# ── same-chapter success across the three branches ────────────────────────────

def test_present_marks_checked_in(cursor, chapter_factory, event_factory, member_factory):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)

    result = set_attendance(cursor, chapter, event, member, "present", officer)
    assert result == {"status": "checked_in", "method": "manual"}

    cursor.execute(
        "SELECT checked_in, method, chapter_id FROM attendance WHERE event_id=%s AND member_id=%s",
        (event, member),
    )
    row = cursor.fetchone()
    assert row["checked_in"] is True
    assert row["method"] == "manual"
    assert str(row["chapter_id"]) == chapter


def test_absent_marks_not_checked_in_and_clears_excuse(
    cursor, chapter_factory, event_factory, member_factory, excuse_factory
):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)
    excuse_factory(chapter, event, member)

    result = set_attendance(cursor, chapter, event, member, "absent", officer)
    assert result == {"status": "absent", "method": "manual"}

    cursor.execute("SELECT checked_in FROM attendance WHERE event_id=%s AND member_id=%s", (event, member))
    assert cursor.fetchone()["checked_in"] is False
    cursor.execute("SELECT count(*) AS n FROM excuses WHERE event_id=%s AND member_id=%s", (event, member))
    assert cursor.fetchone()["n"] == 0


def test_excused_upserts_attendance_and_approved_excuse(
    cursor, chapter_factory, event_factory, member_factory
):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)

    result = set_attendance(cursor, chapter, event, member, "excused", officer, reason="family emergency")
    assert result == {"status": "excused", "method": "manual"}

    cursor.execute("SELECT checked_in FROM attendance WHERE event_id=%s AND member_id=%s", (event, member))
    assert cursor.fetchone()["checked_in"] is False
    cursor.execute(
        "SELECT status, reviewed_by, reason, chapter_id FROM excuses WHERE event_id=%s AND member_id=%s",
        (event, member),
    )
    exc = cursor.fetchone()
    assert exc["status"] == "approved"
    assert str(exc["reviewed_by"]) == officer
    assert exc["reason"] == "family emergency"
    assert str(exc["chapter_id"]) == chapter


def test_excused_requires_reason(cursor, chapter_factory, event_factory, member_factory):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)

    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        set_attendance(cursor, chapter, event, member, "excused", officer, reason="   ")
    assert "reason is required" in str(exc.value)


def test_inactive_member_rejected(cursor, chapter_factory, event_factory, member_factory):
    chapter = chapter_factory()
    event = event_factory(chapter)
    officer = member_factory(chapter=chapter)
    member = member_factory(chapter=chapter)
    cursor.execute("UPDATE members SET status='inactive' WHERE id=%s", (member,))

    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        set_attendance(cursor, chapter, event, member, "present", officer)
    assert "member" in str(exc.value) and "not found in chapter" in str(exc.value)


# ── atomicity of the excused branch ───────────────────────────────────────────

def test_excused_branch_is_atomic(cursor, chapter_factory, event_factory, member_factory):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)

    # Force the excuse INSERT (which happens after the attendance upsert) to fail,
    # scoped to this test's sentinel reason so no other test is affected.
    cursor.execute(
        """
        CREATE OR REPLACE FUNCTION _test_boom_excuses() RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.reason = 'ATOMIC_TEST_TRIGGER' THEN
                RAISE EXCEPTION 'boom';
            END IF;
            RETURN NEW;
        END $$;
        """
    )
    cursor.execute(
        "CREATE TRIGGER _test_boom_excuses_trg BEFORE INSERT ON excuses "
        "FOR EACH ROW EXECUTE FUNCTION _test_boom_excuses()"
    )
    try:
        with pytest.raises(psycopg2.errors.RaiseException):
            set_attendance(cursor, chapter, event, member, "excused", officer,
                           reason="ATOMIC_TEST_TRIGGER")

        # The attendance upsert that ran before the failing excuse insert must be
        # rolled back: no partial rows survive.
        cursor.execute("SELECT count(*) AS n FROM attendance WHERE event_id=%s AND member_id=%s", (event, member))
        assert cursor.fetchone()["n"] == 0
        cursor.execute("SELECT count(*) AS n FROM excuses WHERE event_id=%s AND member_id=%s", (event, member))
        assert cursor.fetchone()["n"] == 0
    finally:
        cursor.execute("DROP TRIGGER IF EXISTS _test_boom_excuses_trg ON excuses")
        cursor.execute("DROP FUNCTION IF EXISTS _test_boom_excuses()")


# ── D3: approving an excuse voids a matching unpaid fine invoice ───────────────

def _create_fine_invoice(cursor, chapter, member, event, amount_cents=2500):
    cursor.execute(
        """
        SELECT tr_create_invoice(
            p_chapter_id := %s, p_member_id := %s, p_kind := 'fine',
            p_amount_cents := %s, p_description := 'Missed required event',
            p_actor_id := NULL, p_source_event_id := %s
        ) AS r
        """,
        (chapter, member, amount_cents, event),
    )
    return cursor.fetchone()["r"]


def test_approve_after_fine_processing_voids_the_invoice(
    cursor, chapter_factory, event_factory, member_factory, excuse_factory
):
    chapter = chapter_factory()
    event = event_factory(chapter, required=True)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)

    invoice = _create_fine_invoice(cursor, chapter, member, event)
    invoice_id = invoice["id"]
    excuse = excuse_factory(chapter, event, member)

    review_excuse(cursor, chapter, excuse, "approved", officer)

    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice_id,))
    assert cursor.fetchone()["status"] == "cancelled"
    cursor.execute(
        "SELECT count(*) AS n FROM big_ledger "
        "WHERE source_table='unpaid_invoices' AND source_id=%s AND entry_type='CANCEL_INVOICE'",
        (invoice_id,),
    )
    assert cursor.fetchone()["n"] == 1


def test_approve_before_fine_processing_is_a_noop_void(
    cursor, chapter_factory, event_factory, member_factory, excuse_factory
):
    chapter = chapter_factory()
    event = event_factory(chapter, required=True)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)
    excuse = excuse_factory(chapter, event, member)

    result = review_excuse(cursor, chapter, excuse, "approved", officer)
    assert result["status"] == "approved"

    # No fine invoice existed, so nothing was voided and nothing was created.
    cursor.execute(
        "SELECT count(*) AS n FROM unpaid_invoices WHERE source_event_id=%s AND member_id=%s",
        (event, member),
    )
    assert cursor.fetchone()["n"] == 0


def test_approve_never_touches_a_paid_invoice(
    cursor, chapter_factory, event_factory, member_factory, excuse_factory
):
    chapter = chapter_factory()
    event = event_factory(chapter, required=True)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)

    invoice = _create_fine_invoice(cursor, chapter, member, event)
    invoice_id = invoice["id"]
    cursor.execute("UPDATE unpaid_invoices SET status='paid' WHERE id=%s", (invoice_id,))
    excuse = excuse_factory(chapter, event, member)

    review_excuse(cursor, chapter, excuse, "approved", officer)

    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice_id,))
    assert cursor.fetchone()["status"] == "paid"


# ── idempotency ───────────────────────────────────────────────────────────────

def test_set_attendance_idempotency_replay(cursor, chapter_factory, event_factory, member_factory):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)
    key = str(uuid.uuid4())

    first = set_attendance(cursor, chapter, event, member, "present", officer, key=key)
    second = set_attendance(cursor, chapter, event, member, "present", officer, key=key)
    assert first == second

    cursor.execute("SELECT id FROM attendance WHERE event_id=%s AND member_id=%s", (event, member))
    att_id = str(cursor.fetchone()["id"])
    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs "
        "WHERE action='ATTENDANCE_OVERRIDDEN' AND target_id=%s",
        (att_id,),
    )
    assert cursor.fetchone()["n"] == 1  # replay short-circuited, no second audit row


def test_review_excuse_idempotency_replay(
    cursor, chapter_factory, event_factory, member_factory, excuse_factory
):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)
    excuse = excuse_factory(chapter, event, member)
    key = str(uuid.uuid4())

    first = review_excuse(cursor, chapter, excuse, "approved", officer, key=key)
    second = review_excuse(cursor, chapter, excuse, "approved", officer, key=key)
    assert first == second

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE action='EXCUSE_REVIEWED' AND target_id=%s",
        (excuse,),
    )
    assert cursor.fetchone()["n"] == 1


# ── audit trail uses the new catalog actions ──────────────────────────────────

def test_audit_logs_written_with_new_actions(
    cursor, chapter_factory, event_factory, member_factory, excuse_factory
):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)
    officer = member_factory(chapter=chapter)

    set_attendance(cursor, chapter, event, member, "present", officer)
    excuse = excuse_factory(chapter, event, member_factory(chapter=chapter))
    review_excuse(cursor, chapter, excuse, "denied", officer)

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND action='ATTENDANCE_OVERRIDDEN'",
        (chapter,),
    )
    assert cursor.fetchone()["n"] == 1
    cursor.execute(
        "SELECT metadata FROM audit_logs WHERE chapter_id=%s AND action='EXCUSE_REVIEWED'",
        (chapter,),
    )
    row = cursor.fetchone()
    assert row is not None
    assert row["metadata"]["decision"] == "denied"


# ── D2 derive/validate trigger ────────────────────────────────────────────────

def test_direct_insert_with_mismatched_chapter_raises(
    cursor, chapter_factory, event_factory, member_factory
):
    chapter_a = chapter_factory()
    chapter_b = chapter_factory()
    event_a = event_factory(chapter_a)
    member_a = member_factory(chapter=chapter_a)

    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        cursor.execute(
            "INSERT INTO attendance (chapter_id, event_id, member_id, checked_in) VALUES (%s, %s, %s, TRUE)",
            (chapter_b, event_a, member_a),
        )
    assert "does not match event chapter" in str(exc.value)


def test_direct_insert_without_chapter_derives_it(
    cursor, chapter_factory, event_factory, member_factory
):
    chapter = chapter_factory()
    event = event_factory(chapter)
    member = member_factory(chapter=chapter)

    cursor.execute(
        "INSERT INTO attendance (event_id, member_id, checked_in) VALUES (%s, %s, TRUE) RETURNING chapter_id",
        (event, member),
    )
    assert str(cursor.fetchone()["chapter_id"]) == chapter
