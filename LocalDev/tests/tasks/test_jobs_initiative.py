"""Job/initiative seams added in Events V1 Phase 3 (docs/imp-ev-ph3.md §5.2,
items 9-12). Storage/RPCs stay tasks/tk_* (D11); initiatives are a calendar
peer of events with the officer layer omitted (D8).
"""

from __future__ import annotations

import uuid

import pytest

from api.tasks.services.approvals import can_approve_job
from tests.tasks.conftest import commit_task, uncommit_task


def create_task_rpc(
    cursor,
    chapter_id,
    *,
    title=None,
    actor_id,
    event_id=None,
    initiative_id=None,
    key=None,
):
    cursor.execute(
        "SELECT tk_create_task(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS r",
        (
            chapter_id,
            title or f"Job {uuid.uuid4().hex[:8]}",
            None,
            None,
            None,
            False,
            None,
            actor_id,
            key,
            event_id,
            initiative_id,
        ),
    )
    return cursor.fetchone()["r"]


def report_done(cursor, chapter_id, task_id, member_id, key=None):
    cursor.execute(
        "SELECT tk_report_done(%s, %s, %s, %s) AS r", (chapter_id, task_id, member_id, key)
    )
    return cursor.fetchone()["r"]


def approve_task(cursor, chapter_id, task_id, actor_id, key=None):
    cursor.execute(
        "SELECT tk_approve_task(%s, %s, %s, %s) AS r", (chapter_id, task_id, actor_id, key)
    )
    return cursor.fetchone()["r"]


def _outbox(cursor, task_id, event_type):
    cursor.execute(
        "SELECT member_id, dedup_key, payload FROM message_outbox "
        "WHERE target_table = 'tasks' AND target_id = %s AND event_type = %s",
        (task_id, event_type),
    )
    return cursor.fetchall()


# ── 9. task_two_parents / initiative_not_found ───────────────────────────────


def test_create_task_with_both_parents_raises_two_parents(
    cursor, chapter_id, member_id, event_factory, initiative_factory
):
    event_id = event_factory(hours_from_now=72)
    initiative_id = initiative_factory(hours_from_now=72)

    with pytest.raises(Exception, match="task_two_parents"):
        create_task_rpc(
            cursor, chapter_id, actor_id=member_id, event_id=event_id, initiative_id=initiative_id
        )


def test_create_task_with_foreign_chapter_initiative_raises_initiative_not_found(
    cursor, chapter_id, member_id
):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES ('other-jobs', 'o', 's') RETURNING id"
    )
    other_chapter = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO members (chapter_id, name, email, role, status) "
        "VALUES (%s, 'Foreign Creator', %s, 'member', 'active') RETURNING id",
        (other_chapter, f"{uuid.uuid4()}@test.local"),
    )
    foreign_creator = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO initiatives (chapter_id, title, date, time, created_by) "
        "VALUES (%s, 'Foreign Initiative', '2026-07-01', '10:00', %s) RETURNING id",
        (other_chapter, foreign_creator),
    )
    foreign_initiative = str(cursor.fetchone()["id"])

    with pytest.raises(Exception, match="initiative_not_found"):
        create_task_rpc(cursor, chapter_id, actor_id=member_id, initiative_id=foreign_initiative)


# ── 10. T-36h hard lock anchors on initiative start too ──────────────────────


def test_t36h_lock_blocks_uncommit_inside_window(
    cursor, chapter_id, member_factory, task_factory, initiative_factory
):
    initiative_id = initiative_factory(hours_from_now=12)  # inside T-36h
    task_id = task_factory(initiative_id=initiative_id)
    claimant = member_factory()

    commit_task(cursor, chapter_id, task_id, claimant)
    with pytest.raises(Exception, match="unclaim_locked"):
        uncommit_task(cursor, chapter_id, task_id, claimant)


def test_uncommit_succeeds_outside_t36h_window(
    cursor, chapter_id, member_factory, task_factory, initiative_factory
):
    initiative_id = initiative_factory(hours_from_now=72)  # outside T-36h
    task_id = task_factory(initiative_id=initiative_id)
    claimant = member_factory()

    commit_task(cursor, chapter_id, task_id, claimant)
    result = uncommit_task(cursor, chapter_id, task_id, claimant)
    assert result["task_status"] == "open"


# ── 11. approval authorization ────────────────────────────────────────────────


def test_assigned_chair_can_approve_initiative_job(
    sb_client, cursor, chapter_id, member_factory, task_factory, initiative_factory
):
    chair = member_factory()
    initiative_id = initiative_factory(hours_from_now=72, chairs=[chair])
    task_id = task_factory(initiative_id=initiative_id)
    claimant = member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)
    report_done(cursor, chapter_id, task_id, claimant)

    cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    task = dict(cursor.fetchone())
    task["initiative_id"] = str(task["initiative_id"])

    chair_user = {"id": chair, "chapter_id": chapter_id, "role": "member"}
    assert can_approve_job(sb_client, user=chair_user, task=task) is True

    result = approve_task(cursor, chapter_id, task_id, chair)
    assert result["status"] == "approved"


def test_non_chair_without_tasks_review_cannot_approve_initiative_job(
    sb_client, cursor, chapter_id, member_factory, task_factory, initiative_factory
):
    chair = member_factory()
    initiative_id = initiative_factory(hours_from_now=72, chairs=[chair])
    task_id = task_factory(initiative_id=initiative_id)
    claimant = member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)
    report_done(cursor, chapter_id, task_id, claimant)

    cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    task = dict(cursor.fetchone())
    task["initiative_id"] = str(task["initiative_id"])

    outsider = member_factory()
    outsider_user = {"id": outsider, "chapter_id": chapter_id, "role": "member"}
    assert can_approve_job(sb_client, user=outsider_user, task=task) is False


# ── 12. tk_report_done fans JOB_REPORTED to initiative_chairs ────────────────


def test_report_done_notifies_initiative_chairs(
    cursor, chapter_id, member_factory, task_factory, initiative_factory
):
    chair1, chair2 = member_factory(), member_factory()
    initiative_id = initiative_factory(hours_from_now=72, chairs=[chair1, chair2])
    task_id = task_factory(initiative_id=initiative_id)
    claimant = member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)

    report_done(cursor, chapter_id, task_id, claimant)
    rows = _outbox(cursor, task_id, "JOB_REPORTED")
    assert {str(r["member_id"]) for r in rows} == {chair1, chair2}


def test_report_done_initiative_outbox_dedups_on_replay(
    cursor, chapter_id, member_factory, task_factory, initiative_factory
):
    chair = member_factory()
    initiative_id = initiative_factory(hours_from_now=72, chairs=[chair])
    task_id = task_factory(initiative_id=initiative_id)
    claimant = member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)
    key = f"k-{uuid.uuid4()}"

    report_done(cursor, chapter_id, task_id, claimant, key=key)
    report_done(cursor, chapter_id, task_id, claimant, key=key)  # idempotent replay

    rows = _outbox(cursor, task_id, "JOB_REPORTED")
    assert len(rows) == 1
