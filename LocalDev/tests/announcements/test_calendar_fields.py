"""Announcement calendar slot + DELETE (B4FEND §5.2, D15).

calendar_date/calendar_time are calendar PRESENCE, not a scheduled send — send
still happens on POST /{id}/send and the SMS blast on POST /{id}/send-sms.
DELETE drops a draft outright and merely retires a sent row from the calendar.
"""

from __future__ import annotations

import uuid


def _row(cursor, announcement_id):
    cursor.execute("SELECT * FROM announcements WHERE id = %s", (announcement_id,))
    return cursor.fetchone()


def test_create_persists_calendar_slot(as_member, cursor, president):
    resp = as_member(president).post(
        "/api/announcements/",
        json={
            "title": "Rush kickoff",
            "body": "Doors at 7.",
            "calendar_date": "2026-07-05",
            "calendar_time": "18:30:00",
        },
    )
    assert resp.status_code == 200, resp.text
    row = _row(cursor, resp.json()["id"])
    assert str(row["calendar_date"]) == "2026-07-05"
    assert str(row["calendar_time"]) == "18:30:00"
    assert row["hidden_from_calendar"] is False
    assert row["status"] == "draft"  # a date is not a send


def test_create_without_calendar_slot_still_works(as_member, cursor, president):
    """Existing callers (no calendar fields) keep creating plain feed posts."""
    resp = as_member(president).post(
        "/api/announcements/", json={"title": "FYI", "body": "No date."}
    )
    assert resp.status_code == 200, resp.text
    row = _row(cursor, resp.json()["id"])
    assert row["calendar_date"] is None and row["calendar_time"] is None


def test_calendar_time_without_date_is_422(as_member, president):
    resp = as_member(president).post(
        "/api/announcements/",
        json={"title": "Bad", "body": "Body", "calendar_time": "18:30:00"},
    )
    assert resp.status_code == 422, resp.text


def test_delete_draft_removes_the_row(as_member, cursor, president, announcement_factory):
    draft = announcement_factory(status="draft")
    resp = as_member(president).delete(f"/api/announcements/{draft}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True
    assert _row(cursor, draft) is None


def test_delete_sent_hides_it_and_is_idempotent(
    as_member, cursor, president, announcement_factory
):
    sent = announcement_factory(status="sent")
    client = as_member(president)

    first = client.delete(f"/api/announcements/{sent}")
    assert first.status_code == 200, first.text
    assert first.json() == {"id": sent, "deleted": False, "hidden_from_calendar": True}

    row = _row(cursor, sent)
    assert row is not None                      # the feed post / SMS record stays
    assert row["hidden_from_calendar"] is True
    assert row["status"] == "sent" and row["sent_at"] is not None

    second = client.delete(f"/api/announcements/{sent}")
    assert second.status_code == 200, second.text
    assert _row(cursor, sent)["hidden_from_calendar"] is True


def test_delete_cross_chapter_is_404(as_member, cursor, president):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) "
        "VALUES (%s, 'Other Org', 'Other U') RETURNING id",
        (f"other-{uuid.uuid4()}",),
    )
    other_chapter = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO announcements (chapter_id, title, body, audience, status) "
        "VALUES (%s, 'Theirs', 'Body', 'chapter', 'sent') RETURNING id",
        (other_chapter,),
    )
    foreign = str(cursor.fetchone()["id"])

    resp = as_member(president).delete(f"/api/announcements/{foreign}")
    assert resp.status_code == 404, resp.text


def test_plain_member_cannot_delete(as_member, member_factory, announcement_factory):
    sent = announcement_factory(status="sent")
    resp = as_member(member_factory()).delete(f"/api/announcements/{sent}")
    assert resp.status_code == 403, resp.text
