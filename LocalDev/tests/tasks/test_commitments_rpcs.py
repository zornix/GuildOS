"""tk_commit_task / tk_uncommit_task / completion — DB-backed RPC tests.

Spec §4 (GreekV1): volunteering, the 24h-before-event late-uncommit rule
(resolved decision #1), social-accountability log, attribution inputs.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from tests.tasks.conftest import commit_task, uncommit_task


# ── commit ────────────────────────────────────────────────────────────────────


def test_commit_creates_active_commitment_log_and_status(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()

    result = commit_task(cursor, chapter_id, task_id, member_id)

    assert result["commitment"]["status"] == "active"
    assert result["commitment"]["member_id"] == member_id
    assert result["task_status"] == "in_progress"

    cursor.execute(
        "SELECT * FROM task_commitments WHERE task_id = %s AND member_id = %s",
        (task_id, member_id),
    )
    rows = cursor.fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "active"

    cursor.execute(
        "SELECT * FROM task_commitment_log WHERE task_id = %s AND member_id = %s",
        (task_id, member_id),
    )
    log = cursor.fetchall()
    assert len(log) == 1
    assert log[0]["action"] == "commit"
    assert log[0]["late"] is False

    cursor.execute("SELECT status FROM tasks WHERE id = %s", (task_id,))
    assert cursor.fetchone()["status"] == "in_progress"


def test_double_commit_rejected_cleanly(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)

    with pytest.raises(Exception, match="active commitment"):
        commit_task(cursor, chapter_id, task_id, member_id)


def test_commit_idempotency_key_returns_cached_result(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    key = f"k-{uuid.uuid4()}"

    first = commit_task(cursor, chapter_id, task_id, member_id, key=key)
    second = commit_task(cursor, chapter_id, task_id, member_id, key=key)

    assert first["commitment"]["id"] == second["commitment"]["id"]
    cursor.execute("SELECT count(*) AS n FROM task_commitments WHERE task_id = %s", (task_id,))
    assert cursor.fetchone()["n"] == 1


def test_second_member_can_commit_same_task(cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory(people_needed=2)
    m1, m2 = member_factory(), member_factory()

    commit_task(cursor, chapter_id, task_id, m1)
    result = commit_task(cursor, chapter_id, task_id, m2)

    assert result["commitment"]["member_id"] == m2
    cursor.execute(
        "SELECT count(*) AS n FROM task_commitments WHERE task_id = %s AND status = 'active'",
        (task_id,),
    )
    assert cursor.fetchone()["n"] == 2


def test_commit_rejected_for_done_or_cancelled_task(cursor, chapter_id, member_id, task_factory):
    for status in ("done", "cancelled"):
        task_id = task_factory(status=status)
        with pytest.raises(Exception, match="cannot be committed"):
            commit_task(cursor, chapter_id, task_id, member_id)


def test_commit_rejects_member_outside_chapter(cursor, chapter_id, member_factory, task_factory):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES ('other', 'o', 's') RETURNING id"
    )
    other_chapter = str(cursor.fetchone()["id"])
    outsider = member_factory(chapter=other_chapter)
    task_id = task_factory()

    with pytest.raises(Exception, match="not in chapter"):
        commit_task(cursor, chapter_id, task_id, outsider)


def test_commit_rejects_inactive_member(cursor, chapter_id, member_factory, task_factory):
    member = member_factory()
    cursor.execute("UPDATE members SET status = 'inactive' WHERE id = %s", (member,))
    task_id = task_factory()

    with pytest.raises(psycopg2.Error, match="not an active member"):
        commit_task(cursor, chapter_id, task_id, member)


def test_invited_member_can_commit(cursor, chapter_id, member_factory, task_factory):
    member = member_factory()
    cursor.execute("UPDATE members SET status = 'invited' WHERE id = %s", (member,))
    task_id = task_factory()

    result = commit_task(cursor, chapter_id, task_id, member)
    assert result["commitment"]["status"] == "active"


def test_recommit_after_uncommit_is_allowed(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    uncommit_task(cursor, chapter_id, task_id, member_id)

    result = commit_task(cursor, chapter_id, task_id, member_id)
    assert result["commitment"]["status"] == "active"


# ── uncommit & the hard T-36h lock (decision D2) ─────────────────────────────────────────────


def test_uncommit_more_than_36h_before_event_succeeds(
    cursor, chapter_id, member_id, task_factory, event_factory
):
    event_id = event_factory(hours_from_now=48)
    task_id = task_factory(event_id=event_id)
    commit_task(cursor, chapter_id, task_id, member_id)

    result = uncommit_task(cursor, chapter_id, task_id, member_id, reason="schedule conflict")

    assert result["commitment"]["status"] == "uncommitted"
    assert 47 < float(result["hours_before_event"]) < 49


def test_uncommit_within_36h_of_event_start_is_locked(
    cursor, chapter_id, member_id, task_factory, event_factory
):
    event_id = event_factory(hours_from_now=10)
    task_id = task_factory(event_id=event_id)
    commit_task(cursor, chapter_id, task_id, member_id)

    with pytest.raises(Exception, match="unclaim_locked"):
        uncommit_task(cursor, chapter_id, task_id, member_id)


def test_uncommit_after_event_passed_is_locked(cursor, chapter_id, member_id, task_factory, event_factory):
    event_id = event_factory(hours_from_now=-5)
    task_id = task_factory(event_id=event_id)
    commit_task(cursor, chapter_id, task_id, member_id)

    with pytest.raises(Exception, match="unclaim_locked"):
        uncommit_task(cursor, chapter_id, task_id, member_id)


def test_uncommit_standalone_task_is_never_locked(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)

    result = uncommit_task(cursor, chapter_id, task_id, member_id)

    assert result["commitment"]["status"] == "uncommitted"
    assert result["hours_before_event"] is None


def test_uncommit_outside_lock_logs_reason_and_event(
    cursor, chapter_id, member_id, task_factory, event_factory
):
    """A permitted (outside T-36h) uncommit is logged with its reason + event."""
    event_id = event_factory(hours_from_now=48)
    task_id = task_factory(event_id=event_id)
    commit_task(cursor, chapter_id, task_id, member_id)

    result = uncommit_task(cursor, chapter_id, task_id, member_id, reason="emergency")
    assert result["commitment"]["status"] == "uncommitted"

    cursor.execute(
        "SELECT reason, event_id FROM task_commitment_log WHERE task_id = %s AND action = 'uncommit'",
        (task_id,),
    )
    row = cursor.fetchone()
    assert row["reason"] == "emergency"
    assert str(row["event_id"]) == event_id


def test_task_returns_to_open_when_last_member_uncommits(
    cursor, chapter_id, member_factory, task_factory
):
    task_id = task_factory(people_needed=2)
    m1, m2 = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, m1)
    commit_task(cursor, chapter_id, task_id, m2)

    first = uncommit_task(cursor, chapter_id, task_id, m1)
    assert first["task_status"] == "in_progress"  # m2 still holds it

    second = uncommit_task(cursor, chapter_id, task_id, m2)
    assert second["task_status"] == "open"
    cursor.execute("SELECT status FROM tasks WHERE id = %s", (task_id,))
    assert cursor.fetchone()["status"] == "open"


def test_uncommit_without_active_commitment_raises(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    with pytest.raises(Exception, match="no active commitment"):
        uncommit_task(cursor, chapter_id, task_id, member_id)


def test_uncommit_idempotency_key_returns_cached_result(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    key = f"k-{uuid.uuid4()}"

    first = uncommit_task(cursor, chapter_id, task_id, member_id, key=key)
    second = uncommit_task(cursor, chapter_id, task_id, member_id, key=key)
    assert first["commitment"]["id"] == second["commitment"]["id"]


# ── completion ───────────────────────────────────────────────────────────────


def test_done_marks_active_commitments_completed(cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory(people_needed=2)
    m1, m2 = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, m1)
    commit_task(cursor, chapter_id, task_id, m2)

    cursor.execute(
        "SELECT tk_update_task_status(%s, %s, 'done', %s) AS r",
        (chapter_id, task_id, m1),
    )
    assert cursor.fetchone()["r"]["status"] == "done"

    cursor.execute(
        "SELECT status, count(*) AS n FROM task_commitments WHERE task_id = %s GROUP BY status",
        (task_id,),
    )
    rows = {r["status"]: r["n"] for r in cursor.fetchall()}
    assert rows == {"completed": 2}


def test_uncommitted_member_not_credited_on_completion(cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory(people_needed=2)
    m1, m2 = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, m1)
    commit_task(cursor, chapter_id, task_id, m2)
    uncommit_task(cursor, chapter_id, task_id, m2)

    cursor.execute(
        "SELECT tk_update_task_status(%s, %s, 'done', %s) AS r", (chapter_id, task_id, m1)
    )
    cursor.fetchone()

    cursor.execute(
        "SELECT member_id, status FROM task_commitments WHERE task_id = %s", (task_id,)
    )
    statuses = {str(r["member_id"]): r["status"] for r in cursor.fetchall()}
    assert statuses[m1] == "completed"
    assert statuses[m2] == "uncommitted"


def test_tasks_status_check_allows_committed(cursor, chapter_id, task_factory):
    # drop+recreate of the constraint must keep legacy values AND allow 'committed'
    for status in ("open", "in_progress", "done", "cancelled", "committed"):
        task_factory(status=status)
    with pytest.raises(Exception, match="tasks_status_check"):
        task_factory(status="bogus")


# ── audit & append-only ──────────────────────────────────────────────────────


def test_audit_logs_written_for_commit_and_uncommit(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    uncommit_task(cursor, chapter_id, task_id, member_id)

    cursor.execute(
        "SELECT action FROM audit_logs WHERE chapter_id = %s AND target_table = 'tasks' "
        "AND target_id = %s ORDER BY created_at",
        (chapter_id, task_id),
    )
    actions = [r["action"] for r in cursor.fetchall()]
    assert "COMMIT_TASK" in actions
    assert "UNCOMMIT_TASK" in actions


def test_commitment_log_is_append_only(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)

    with pytest.raises(Exception, match="append-only"):
        cursor.execute(
            "UPDATE task_commitment_log SET late = true WHERE task_id = %s", (task_id,)
        )
    with pytest.raises(Exception, match="append-only|forbidden"):
        cursor.execute("DELETE FROM task_commitment_log WHERE task_id = %s", (task_id,))


def test_commit_rejects_task_from_other_chapter(cursor, chapter_id, member_id, task_factory):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES ('other2', 'o', 's') RETURNING id"
    )
    other_chapter = str(cursor.fetchone()["id"])
    foreign_task = task_factory(chapter=other_chapter)

    with pytest.raises(Exception, match="not found"):
        commit_task(cursor, chapter_id, foreign_task, member_id)
