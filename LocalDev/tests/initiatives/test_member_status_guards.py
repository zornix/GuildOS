"""Initiative creation applies the same member status guard as chair addition."""

import psycopg2
import pytest


@pytest.mark.parametrize("status", ["inactive", "alumni"])
def test_create_initiative_rejects_ineligible_cochair(
    cursor, chapter_id, member_factory, status
):
    actor = member_factory()
    chair = member_factory()
    cursor.execute("UPDATE members SET status = %s WHERE id = %s", (status, chair))
    with pytest.raises(psycopg2.Error, match=f"member {chair} is not an active member"):
        cursor.execute(
            "SELECT in_create_initiative(%s, 'Status guard', NULL, CURRENT_DATE, "
            "TIME '19:00', NULL, NULL, %s::uuid[], %s, NULL)",
            (chapter_id, [chair], actor),
        )


@pytest.mark.parametrize("operation", ["in_add_chair", "in_remove_chair"])
def test_chair_changes_do_not_block_unrelated_child_inserts(
    db_url, cursor, chapter_id, member_factory, operation
):
    actor = member_factory()
    chair = member_factory()
    cursor.execute(
        "SELECT in_create_initiative(%s, 'Lock guard', NULL, CURRENT_DATE, "
        "TIME '19:00', NULL, NULL, %s::uuid[], %s, NULL)",
        (chapter_id, [chair] if operation == "in_remove_chair" else [], actor),
    )
    initiative_id = cursor.fetchone()["in_create_initiative"]["id"]
    change = psycopg2.connect(db_url, connect_timeout=15)
    insert = psycopg2.connect(db_url, connect_timeout=15)
    try:
        with change.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '2s'")
            # Only these two fixed function names are interpolated.
            cur.execute(
                f"SELECT {operation}(%s, %s, %s, %s, NULL)",
                (chapter_id, initiative_id, chair, actor),
            )
        with insert.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '500ms'")
            cur.execute(
                "INSERT INTO tasks (chapter_id, initiative_id, title) "
                "VALUES (%s, %s, 'Unrelated child') RETURNING initiative_id",
                (chapter_id, initiative_id),
            )
            assert str(cur.fetchone()[0]) == initiative_id
    finally:
        insert.rollback()
        insert.close()
        change.rollback()
        change.close()
