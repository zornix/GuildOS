"""Database guard for one live event fine per member."""
import psycopg2
import pytest


def _fine(cursor, chapter_id, member_id, event_id):
    cursor.execute(
        """INSERT INTO unpaid_invoices
           (chapter_id, member_id, kind, amount_cents, source_event_id, status)
           VALUES (%s, %s, 'fine', 2500, %s, 'unpaid') RETURNING id""",
        (chapter_id, member_id, event_id),
    )
    return str(cursor.fetchone()["id"])


@pytest.fixture
def fine_event(cursor, chapter_id):
    cursor.execute(
        "INSERT INTO events (chapter_id,title,date,time,location,required) "
        "VALUES (%s,'Fine guard',CURRENT_DATE,TIME '20:00','Hall',true) RETURNING id",
        (chapter_id,),
    )
    return str(cursor.fetchone()["id"])


def test_second_live_fine_for_same_event_and_member_is_rejected(cursor, chapter_id, member_id, fine_event):
    _fine(cursor, chapter_id, member_id, fine_event)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _fine(cursor, chapter_id, member_id, fine_event)


def test_a_new_fine_is_allowed_after_the_first_is_cancelled(cursor, chapter_id, member_id, fine_event):
    first = _fine(cursor, chapter_id, member_id, fine_event)
    cursor.execute("UPDATE unpaid_invoices SET status='cancelled' WHERE id=%s", (first,))
    assert _fine(cursor, chapter_id, member_id, fine_event) != first


def test_free_form_fines_without_an_event_are_not_limited(cursor, chapter_id, member_id):
    assert _fine(cursor, chapter_id, member_id, None) != _fine(cursor, chapter_id, member_id, None)


def test_issuing_skips_a_member_whose_fine_was_already_handled(cursor, chapter_id, member_id, fine_event):
    """A voided or waived fine counts as handled: re-issuing must skip, not report a stale invoice."""
    import json
    first = _fine(cursor, chapter_id, member_id, fine_event)
    cursor.execute("UPDATE unpaid_invoices SET status='cancelled' WHERE id=%s", (first,))
    cursor.execute(
        "SELECT tr_issue_event_fines(%s,%s,%s::jsonb,2500,'Missed',%s) AS r",
        (chapter_id, fine_event, json.dumps([member_id]), member_id),
    )
    result = cursor.fetchone()["r"]
    assert (result["issued"], result["skipped_member_ids"]) == ([], [member_id])
    cursor.execute("SELECT count(*) AS n FROM unpaid_invoices WHERE source_event_id=%s AND member_id=%s", (fine_event, member_id))
    assert cursor.fetchone()["n"] == 1
