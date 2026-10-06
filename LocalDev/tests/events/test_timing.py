from datetime import date, datetime, time, timezone
from api.events.core.timing import event_start_utc, has_started

LA = "America/Los_Angeles"


def test_start_is_local_time_converted_to_utc():
    assert event_start_utc(
        {"date": date(2026, 10, 5), "time": time(20)}, LA
    ) == datetime(2026, 10, 6, 3, tzinfo=timezone.utc)


def test_strings_are_accepted():
    assert event_start_utc({"date": "2026-10-05", "time": "20:00:00"}, LA) == datetime(
        2026, 10, 6, 3, tzinfo=timezone.utc
    )


def test_missing_time_means_end_of_local_day():
    assert event_start_utc({"date": date(2026, 10, 5), "time": None}, LA) == datetime(
        2026, 10, 6, 6, 59, 59, tzinfo=timezone.utc
    )


def test_has_started():
    event = {"date": date(2026, 10, 5), "time": time(20)}
    assert not has_started(event, LA, datetime(2026, 10, 5, 16, tzinfo=timezone.utc))
    assert has_started(event, LA, datetime(2026, 10, 6, 3, 1, tzinfo=timezone.utc))


def test_chapter_timezone_falls_back_for_missing_or_invalid_zone():
    from unittest.mock import Mock
    from api.events.core.timing import chapter_timezone, DEFAULT_TZ

    sb = Mock()
    for row in (None, {"timezone": None}, {"timezone": "Unknown/Zone"}):
        sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = row
        assert chapter_timezone(sb, "chapter") == DEFAULT_TZ
    sb.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {
        "timezone": "America/New_York"
    }
    assert chapter_timezone(sb, "chapter") == "America/New_York"
