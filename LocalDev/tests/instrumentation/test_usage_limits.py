"""F-048: usage tracker name, metadata, rate, and retention bounds (D13)."""

from __future__ import annotations

import psycopg2
import pytest

import api.instrumentation.services.usage as usage


def _count(cursor, member_id) -> int:
    cursor.execute(
        "SELECT count(*) AS n FROM usage_events WHERE member_id = %s",
        (member_id,),
    )
    return cursor.fetchone()["n"]


def test_bad_event_name_is_dropped(sb_client, cursor, chapter_id, member_id):
    usage.track(sb_client, chapter_id, member_id, "x" * 200)
    usage.track(sb_client, chapter_id, member_id, "DROP TABLE; --")
    assert _count(cursor, member_id) == 0


def test_metadata_over_1kb_is_truncated(sb_client, cursor, chapter_id, member_id):
    usage.track(
        sb_client,
        chapter_id,
        member_id,
        "tab:opened",
        {"blob": "y" * 2000},
    )
    cursor.execute(
        "SELECT metadata FROM usage_events WHERE member_id = %s",
        (member_id,),
    )
    assert cursor.fetchone()["metadata"] == {"_truncated": True}


def test_per_member_hourly_cap(monkeypatch, sb_client, cursor, chapter_id, member_id):
    monkeypatch.setattr(usage, "MAX_EVENTS_PER_MEMBER_PER_HOUR", 3)
    for _ in range(5):
        usage.track(sb_client, chapter_id, member_id, "tab:opened")
    assert _count(cursor, member_id) == 3


def test_usage_rows_can_be_deleted_but_not_updated(sb_client, cursor, chapter_id, member_id):
    usage.track(sb_client, chapter_id, member_id, "tab:opened")
    with pytest.raises(psycopg2.Error):
        cursor.execute(
            "UPDATE usage_events SET event_name = 'x' WHERE member_id = %s",
            (member_id,),
        )
    cursor.execute("DELETE FROM usage_events WHERE member_id = %s", (member_id,))
    assert _count(cursor, member_id) == 0


def test_deleting_a_member_is_not_blocked_by_usage_events(
    sb_client, cursor, chapter_id, member_id
):
    usage.track(sb_client, chapter_id, member_id, "tab:opened")
    cursor.execute("DELETE FROM members WHERE id = %s", (member_id,))
    cursor.execute(
        "SELECT count(*) AS n FROM usage_events WHERE chapter_id = %s",
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 0
