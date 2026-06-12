"""Attendance % — derived over required past events (spec §3)."""

from __future__ import annotations

from datetime import date, timedelta

from api.attendance.services.signals import attendance_summary


def _insert_event(cursor, chapter_id, *, days_offset: int, required: bool) -> str:
    cursor.execute(
        """
        INSERT INTO events (chapter_id, title, date, time, location, required)
        VALUES (%s, 'Att Event', %s, '19:00', 'House', %s)
        RETURNING id
        """,
        (chapter_id, (date.today() + timedelta(days=days_offset)).isoformat(), required),
    )
    return str(cursor.fetchone()["id"])


def _check_in(cursor, event_id, member_id, checked_in=True):
    cursor.execute(
        """
        INSERT INTO attendance (event_id, member_id, checked_in, checked_in_at, method)
        VALUES (%s, %s, %s, now(), 'manual')
        """,
        (event_id, member_id, checked_in),
    )


def test_summary_math(sb_client, cursor, chapter_id, member_factory):
    m = member_factory()
    past_required = [_insert_event(cursor, chapter_id, days_offset=-i - 1, required=True) for i in range(4)]
    _insert_event(cursor, chapter_id, days_offset=-1, required=False)  # not counted
    _insert_event(cursor, chapter_id, days_offset=+7, required=True)  # future, not counted

    for ev in past_required[:3]:
        _check_in(cursor, ev, m)
    _check_in(cursor, past_required[3], m, checked_in=False)

    rows = attendance_summary(sb_client, chapter_id=chapter_id)
    row = next(r for r in rows if r["member_id"] == m)
    assert row["total_required_past_events"] == 4
    assert row["attended_required"] == 3
    assert row["attendance_pct"] == 75.0


def test_summary_filters_to_single_member(sb_client, cursor, chapter_id, member_factory):
    a = member_factory()
    b = member_factory()
    ev = _insert_event(cursor, chapter_id, days_offset=-1, required=True)
    _check_in(cursor, ev, a)

    rows = attendance_summary(sb_client, chapter_id=chapter_id, member_id=a)
    assert [r["member_id"] for r in rows] == [a]
    assert rows[0]["attendance_pct"] == 100.0

    rows_b = attendance_summary(sb_client, chapter_id=chapter_id, member_id=b)
    assert rows_b[0]["attended_required"] == 0
    assert rows_b[0]["attendance_pct"] == 0.0


def test_summary_with_no_required_events(sb_client, chapter_id, member_factory):
    m = member_factory()
    rows = attendance_summary(sb_client, chapter_id=chapter_id, member_id=m)
    assert rows[0]["total_required_past_events"] == 0
    assert rows[0]["attendance_pct"] is None
