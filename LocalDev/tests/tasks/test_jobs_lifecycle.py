"""Jobs V1 Phase 1 — capacity, report/approve/reject lifecycle, outbox, audit.

RPC-level tests (superuser connection bypasses RLS, per the treasury pattern).
Storage/RPCs stay tasks/tk_* (decision D1); the user-facing layer says "job".
"""

from __future__ import annotations

import uuid

import pytest

from tests.tasks.conftest import commit_task, uncommit_task


# ── local RPC helpers ─────────────────────────────────────────────────────────


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


def reject_task(cursor, chapter_id, task_id, actor_id, reason, key=None):
    cursor.execute(
        "SELECT tk_reject_task(%s, %s, %s, %s, %s) AS r",
        (chapter_id, task_id, actor_id, reason, key),
    )
    return cursor.fetchone()["r"]


def _status(cursor, task_id):
    cursor.execute("SELECT status FROM tasks WHERE id = %s", (task_id,))
    return cursor.fetchone()["status"]


def _active_count(cursor, task_id):
    cursor.execute(
        "SELECT count(*) AS n FROM task_commitments WHERE task_id = %s AND status = 'active'",
        (task_id,),
    )
    return cursor.fetchone()["n"]


def _outbox(cursor, task_id, event_type):
    cursor.execute(
        "SELECT member_id, dedup_key, payload FROM message_outbox "
        "WHERE target_table = 'tasks' AND target_id = %s AND event_type = %s",
        (task_id, event_type),
    )
    return cursor.fetchall()


# ── capacity ──────────────────────────────────────────────────────────────────


def test_capacity_blocks_over_fill(cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory(people_needed=2)
    m1, m2, m3 = member_factory(), member_factory(), member_factory()

    commit_task(cursor, chapter_id, task_id, m1)
    commit_task(cursor, chapter_id, task_id, m2)
    with pytest.raises(Exception, match="job_full"):
        commit_task(cursor, chapter_id, task_id, m3)

    cursor.execute("SELECT people_needed FROM tasks WHERE id = %s", (task_id,))
    assert cursor.fetchone()["people_needed"] == 2
    assert _active_count(cursor, task_id) == 2  # fill state: 2/2


# ── open ↔ in_progress transitions ────────────────────────────────────────────


def test_first_claim_starts_progress_last_uncommit_reopens(
    cursor, chapter_id, member_id, task_factory
):
    task_id = task_factory()
    assert _status(cursor, task_id) == "open"
    commit_task(cursor, chapter_id, task_id, member_id)
    assert _status(cursor, task_id) == "in_progress"

    uncommit_task(cursor, chapter_id, task_id, member_id)  # standalone: no lock
    assert _status(cursor, task_id) == "open"


# ── T-36h hard lock ───────────────────────────────────────────────────────────


def test_t36h_lock_blocks_uncommit_but_not_claim(
    cursor, chapter_id, member_factory, task_factory, event_factory
):
    event_id = event_factory(hours_from_now=10)  # inside T-36h
    task_id = task_factory(event_id=event_id, people_needed=2)
    m1, m2 = member_factory(), member_factory()

    commit_task(cursor, chapter_id, task_id, m1)
    # Claiming stays open inside the window.
    commit_task(cursor, chapter_id, task_id, m2)
    # Unclaiming is locked.
    with pytest.raises(Exception, match="unclaim_locked"):
        uncommit_task(cursor, chapter_id, task_id, m1)


# ── report done ───────────────────────────────────────────────────────────────


def test_report_done_lifecycle_and_guards(cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory()
    claimant, outsider = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)

    # Non-claimant cannot report.
    with pytest.raises(Exception, match="no active commitment"):
        report_done(cursor, chapter_id, task_id, outsider)

    result = report_done(cursor, chapter_id, task_id, claimant)
    assert result["status"] == "done_reported"
    assert str(result["reported_by"]) == claimant

    # A second report finds done_reported → already_reported.
    with pytest.raises(Exception, match="already_reported"):
        report_done(cursor, chapter_id, task_id, claimant)


def test_report_done_idempotency_replays(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    key = f"k-{uuid.uuid4()}"

    first = report_done(cursor, chapter_id, task_id, member_id, key=key)
    second = report_done(cursor, chapter_id, task_id, member_id, key=key)
    assert first["id"] == second["id"]
    assert second["status"] == "done_reported"


def test_report_done_notifies_event_supervisors(
    cursor, chapter_id, member_factory, task_factory, event_factory
):
    event_id = event_factory(hours_from_now=48)
    supervisor = member_factory()
    cursor.execute(
        "INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator) "
        "VALUES (%s, %s, %s, TRUE)",
        (chapter_id, event_id, supervisor),
    )
    task_id = task_factory(event_id=event_id)
    claimant = member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)

    report_done(cursor, chapter_id, task_id, claimant)
    rows = _outbox(cursor, task_id, "JOB_REPORTED")
    assert {str(r["member_id"]) for r in rows} == {supervisor}


# ── approve ───────────────────────────────────────────────────────────────────


def test_approve_completes_commitments_and_notifies(
    cursor, chapter_id, member_factory, task_factory
):
    task_id = task_factory(people_needed=2)
    m1, m2 = member_factory(), member_factory()
    approver = member_factory()
    commit_task(cursor, chapter_id, task_id, m1)
    commit_task(cursor, chapter_id, task_id, m2)
    report_done(cursor, chapter_id, task_id, m1)

    key = f"k-{uuid.uuid4()}"
    result = approve_task(cursor, chapter_id, task_id, approver, key=key)
    assert result["status"] == "approved"
    assert str(result["approved_by"]) == approver

    cursor.execute(
        "SELECT status, count(*) AS n FROM task_commitments WHERE task_id = %s GROUP BY status",
        (task_id,),
    )
    assert {r["status"]: r["n"] for r in cursor.fetchall()} == {"completed": 2}

    rows = _outbox(cursor, task_id, "JOB_APPROVED")
    assert {str(r["member_id"]) for r in rows} == {m1, m2}

    # Re-running with the same idempotency key adds no duplicate outbox rows.
    approve_task(cursor, chapter_id, task_id, approver, key=key)
    assert len(_outbox(cursor, task_id, "JOB_APPROVED")) == 2


# ── reject ────────────────────────────────────────────────────────────────────


def test_reject_requires_reason(cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    report_done(cursor, chapter_id, task_id, member_id)
    approver = member_id

    with pytest.raises(Exception, match="rejection_reason_required"):
        reject_task(cursor, chapter_id, task_id, approver, "   ")


def test_reject_retains_claimants_and_clears_on_next_report(
    cursor, chapter_id, member_factory, task_factory
):
    task_id = task_factory()
    claimant, approver = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)
    report_done(cursor, chapter_id, task_id, claimant)

    rejected = reject_task(cursor, chapter_id, task_id, approver, "Redo the setup")
    assert rejected["status"] == "in_progress"  # claimant retained
    assert rejected["rejection_reason"] == "Redo the setup"
    assert rejected["reported_by"] is None
    assert _active_count(cursor, task_id) == 1

    rows = _outbox(cursor, task_id, "JOB_REJECTED")
    assert {str(r["member_id"]) for r in rows} == {claimant}
    assert rows[0]["payload"]["reason"] == "Redo the setup"

    # Re-report clears the rejection banner (history stays in audit_logs).
    reported = report_done(cursor, chapter_id, task_id, claimant)
    assert reported["status"] == "done_reported"
    assert reported["rejection_reason"] is None
    assert reported["rejected_by"] is None


def test_reject_with_no_active_claimants_reopens(
    cursor, chapter_id, member_factory, task_factory
):
    task_id = task_factory()
    claimant, approver = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)
    report_done(cursor, chapter_id, task_id, claimant)
    # Standalone task → the claimant may uncommit even after reporting.
    uncommit_task(cursor, chapter_id, task_id, claimant)

    rejected = reject_task(cursor, chapter_id, task_id, approver, "No one is on this")
    assert rejected["status"] == "open"


def test_reject_cycle_dedup_keys_are_distinct(
    cursor, chapter_id, member_factory, task_factory
):
    task_id = task_factory()
    claimant, approver = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)

    report_done(cursor, chapter_id, task_id, claimant)
    reject_task(cursor, chapter_id, task_id, approver, "first")
    report_done(cursor, chapter_id, task_id, claimant)
    reject_task(cursor, chapter_id, task_id, approver, "second")

    keys = {r["dedup_key"] for r in _outbox(cursor, task_id, "JOB_REJECTED")}
    assert len(keys) == 2  # one per rejection cycle


# ── status guard & audit ──────────────────────────────────────────────────────


def test_update_status_refuses_lifecycle_states(cursor, chapter_id, task_factory):
    task_id = task_factory()
    for bad in ("done_reported", "approved"):
        with pytest.raises(Exception, match="report/approve"):
            cursor.execute(
                "SELECT tk_update_task_status(%s, %s, %s, %s)", (chapter_id, task_id, bad, None)
            )


def test_audit_written_for_every_transition(cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory()
    claimant, approver = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)
    report_done(cursor, chapter_id, task_id, claimant)
    reject_task(cursor, chapter_id, task_id, approver, "again")
    report_done(cursor, chapter_id, task_id, claimant)
    approve_task(cursor, chapter_id, task_id, approver)

    cursor.execute(
        "SELECT action FROM audit_logs WHERE target_table = 'tasks' AND target_id = %s",
        (task_id,),
    )
    actions = {r["action"] for r in cursor.fetchall()}
    assert {"COMMIT_TASK", "JOB_REPORTED", "JOB_REJECTED", "JOB_APPROVED"} <= actions
