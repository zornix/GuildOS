"""Supervisors obey the D12 active/invited participation guard."""

import psycopg2
import pytest


def _create(cursor, chapter_id, actor):
    cursor.execute(
        "SELECT ev_create_event(%s, 'Status guard', NULL, CURRENT_DATE, TIME '19:00', "
        "'Hall', FALSE, FALSE, 0, NULL, NULL, 'chapter', NULL, NULL, NULL, %s)",
        (chapter_id, actor),
    )
    return cursor.fetchone()["ev_create_event"]


@pytest.mark.parametrize("status", ["inactive", "alumni"])
def test_create_event_rejects_ineligible_creator_supervisor(
    cursor, chapter_id, member_factory, status
):
    actor = member_factory()
    cursor.execute("UPDATE members SET status = %s WHERE id = %s", (status, actor))
    with pytest.raises(psycopg2.Error, match=f"member {actor} is not an active member"):
        _create(cursor, chapter_id, actor)


@pytest.mark.parametrize("status", ["inactive", "alumni"])
def test_add_supervisor_rejects_ineligible_member(
    cursor, chapter_id, member_factory, status
):
    actor = member_factory()
    member = member_factory(role="officer")
    event = _create(cursor, chapter_id, actor)
    cursor.execute("UPDATE members SET status = %s WHERE id = %s", (status, member))
    with pytest.raises(psycopg2.Error, match=f"member {member} is not an active member"):
        cursor.execute(
            "SELECT ev_add_supervisor(%s, %s, %s, '[\"officer\"]'::jsonb, %s, NULL)",
            (chapter_id, event["id"], member, actor),
        )
