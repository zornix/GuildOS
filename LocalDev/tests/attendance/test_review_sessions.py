"""Review regressions for session windows and cancelled events."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from api.attendance.services import checkin_links as links
from api.attendance.services.sessions import create_session


def test_concurrent_session_open_returns_conflict(
    attendance_app, sb_client, cursor, chapter_id, event_factory, member_factory, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from api.platform.postgres import _TableAccessor

    event, actor = event_factory(chapter_id), member_factory(role="officer")
    ready = Barrier(2, timeout=10)
    insert = _TableAccessor.insert

    def synchronized_insert(query, data):
        if query._table == "checkin_links":
            ready.wait()
        return insert(query, data)

    monkeypatch.setattr(_TableAccessor, "insert", synchronized_insert)

    def open_session():
        try:
            return create_session(
                sb_client, chapter_id=chapter_id, event_id=event, mode="short_link",
                closes_at=None, actor_id=actor,
            )
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: open_session(), range(2)))
    successes = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], HTTPException)
    assert failures[0].status_code == 409
    assert failures[0].detail == "A check-in session was just opened for this event. Refresh to see it."
    cursor.execute("SELECT id FROM attendance_sessions WHERE chapter_id=%s AND event_id=%s", (chapter_id, event))
    assert [str(row["id"]) for row in cursor.fetchall()] == [successes[0]["id"]]
    cursor.execute("SELECT id FROM checkin_links WHERE chapter_id=%s AND event_id=%s", (chapter_id, event))
    assert [str(row["id"]) for row in cursor.fetchall()] == [successes[0]["checkin_link_id"]]


@pytest.mark.parametrize("reader", ["single", "chapter", "bulk"])
async def test_closed_session_hides_code_from_readers(
    attendance_app, sb_client, cursor, chapter_id, event_factory, member_factory,
    checkin_link_factory, session_factory, reader
):
    from api.events.services.events import list_upcoming_details
    from tests.treasury.test_v1_helpers import make_user

    event, actor = event_factory(chapter_id), member_factory(role="officer")
    link, _ = checkin_link_factory(event)
    session_factory(chapter_id, event, checkin_link_id=link, closes_in_minutes=-5)
    if reader == "single":
        assert links.get_active_link_for_event(event) is None
    elif reader == "chapter":
        assert links.list_active_links_for_chapter(chapter_id) == []
    else:
        result = list_upcoming_details(sb_client, user=make_user(actor, chapter_id, role="officer"))
        row = next(row for row in result["events"] if row["event_id"] == event)
        assert row["checkin_link"] == {}


async def test_rotated_link_retains_session_close_time(
    attendance_app, sb_client, cursor, chapter_id, event_factory, member_factory
):
    event, actor = event_factory(chapter_id), member_factory(role="officer")
    session = create_session(
        sb_client, chapter_id=chapter_id, event_id=event, mode="short_link",
        closes_at=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), actor_id=actor,
    )
    replacement = links.create_checkin_link(event, actor)
    valid = links.validate_checkin_link(replacement["short_code"])
    assert valid["attendance_session"] is not None
    assert valid["attendance_session"]["id"] == session["id"]
    cursor.execute("UPDATE attendance_sessions SET closes_at=now()-interval '1 minute' WHERE id=%s", (session["id"],))
    assert links.validate_checkin_link(replacement["short_code"]) is None


async def test_cancelled_event_refuses_session(
    attendance_app, sb_client, cursor, chapter_id, event_factory, member_factory
):
    event, actor = event_factory(chapter_id), member_factory(role="officer")
    cursor.execute("UPDATE events SET cancelled=true WHERE id=%s", (event,))
    with pytest.raises(HTTPException) as error:
        create_session(sb_client, chapter_id=chapter_id, event_id=event, mode="manual", closes_at=None, actor_id=actor)
    assert error.value.status_code == 409
    assert error.value.detail == "Event is cancelled"
    cursor.execute("SELECT id FROM attendance_sessions WHERE chapter_id=%s AND event_id=%s", (chapter_id, event))
    assert cursor.fetchall() == []


async def test_cancelled_event_refuses_excuse(
    attendance_app, sb_client, cursor, chapter_id, event_factory, member_factory, monkeypatch
):
    from api.attendance.api import excuses
    from api.attendance.api.schemas import ExcuseCreate
    from tests.treasury.test_v1_helpers import make_user

    monkeypatch.setattr(excuses, "get_db", lambda: sb_client)
    event, member = event_factory(chapter_id), member_factory()
    cursor.execute("UPDATE events SET cancelled=true WHERE id=%s", (event,))
    with pytest.raises(HTTPException) as error:
        excuses.submit_excuse(event, ExcuseCreate(reason="sick"), make_user(member, chapter_id))
    assert error.value.status_code == 409
    assert error.value.detail == "Event is cancelled"
