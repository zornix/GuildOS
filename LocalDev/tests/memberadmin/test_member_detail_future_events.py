from datetime import datetime, timezone

from api.memberadmin.services import member_detail


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 6, 12, tzinfo=timezone.utc).astimezone(tz)


async def test_future_required_events_are_upcoming(
    sb_client, cursor, chapter_id, member_factory, monkeypatch
):
    member = member_factory()
    cursor.execute("UPDATE chapters SET timezone='Pacific/Auckland' WHERE id=%s", (chapter_id,))
    # Frozen now is October 7, 01:00 in the chapter. Cover tomorrow, later
    # today and an event already started.
    events = {}
    for title, day, start in [
        ("Tomorrow", "2026-10-08", "09:00"),
        ("Later today", "2026-10-07", "09:00"),
        ("Started", "2026-10-07", "00:30"),
    ]:
        cursor.execute(
            "INSERT INTO events (chapter_id, title, date, time, location, required) "
            "VALUES (%s, %s, %s, %s, 'Hall', true) RETURNING id",
            (chapter_id, title, day, start),
        )
        events[title] = str(cursor.fetchone()["id"])
    monkeypatch.setattr(member_detail, "get_db", lambda: sb_client)
    monkeypatch.setattr(member_detail, "datetime", FrozenDateTime, raising=False)
    result = member_detail.load_member_event_breakdown(chapter_id, member)
    statuses = {r["event_id"]: r["status"] for r in result["breakdown"]}
    assert statuses[events["Tomorrow"]] == "upcoming"
    assert statuses[events["Later today"]] == "upcoming"
    assert statuses[events["Started"]] == "absent"
