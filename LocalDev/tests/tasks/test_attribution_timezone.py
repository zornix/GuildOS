from datetime import date, datetime, timezone

import pytest

from api.tasks.services import commitments


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 6, 12, tzinfo=timezone.utc).astimezone(tz)


class FrozenServerDate(date):
    @classmethod
    def today(cls):
        return date(2026, 10, 6)


@pytest.mark.parametrize("tz, day, start, expected", [
    ("Pacific/Auckland", "2026-10-07", "00:30", True),
    ("Pacific/Auckland", "2026-10-07", "09:00", False),
    ("Pacific/Honolulu", "2026-10-06", "09:00", False),
    ("Pacific/Honolulu", "2026-10-06", "01:00", True),
])
def test_event_attribution_uses_chapter_start_time(
    sb_client, cursor, chapter_id, monkeypatch, tz, day, start, expected
):
    cursor.execute("UPDATE chapters SET timezone=%s WHERE id=%s", (tz, chapter_id))
    cursor.execute(
        "INSERT INTO events (chapter_id, title, date, time, location) "
        "VALUES (%s, 'Attribution event', %s, %s, 'Hall') RETURNING id",
        (chapter_id, day, start),
    )
    event = str(cursor.fetchone()["id"])
    monkeypatch.setattr(commitments, "date", FrozenServerDate, raising=False)
    monkeypatch.setattr(commitments, "datetime", FrozenDateTime, raising=False)
    result = commitments._past_event_ids(sb_client, chapter_id=chapter_id, event_ids=[event])
    assert (event in result) is expected
