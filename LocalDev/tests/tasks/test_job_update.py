"""PATCH / DELETE /api/tasks/{id} — job edit and cancel (B4FEND §5.3, D16).

Delete is cancel: `tk_cancel_task` flips status to 'cancelled', never removes
the row, and only while the job is still in the To-do column (status='open').
Edit (`tk_update_task`) is open/in_progress only, never touches the parent,
kind or status, and refuses security assignments — those stay on the ev_* RPCs.

Harness mirrors tests/tasks/test_jobs_api.py.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.tasks.conftest import commit_task


@pytest.fixture
def harness(sb_client, monkeypatch):
    """App with the tasks router; all DB access redirected to the test DB."""
    import api.rbac.services.permissions as rbac_permissions
    import api.tasks.api.commitments as commitments_api
    import api.tasks.api.jobs as jobs_api
    import api.tasks.api.tasks as tasks_api
    from api.dependencies import get_current_user
    from api.tasks.api.router import router

    monkeypatch.setattr(tasks_api, "get_db", lambda: sb_client)
    monkeypatch.setattr(commitments_api, "get_db", lambda: sb_client)
    monkeypatch.setattr(jobs_api, "get_db", lambda: sb_client)
    monkeypatch.setattr(rbac_permissions, "get_db", lambda: sb_client)

    app = FastAPI()
    app.include_router(router, prefix="/api/tasks")

    current_user: dict = {}
    app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(app)

    class Harness:
        def login(self, member_id: str, chapter_id: str, role: str = "member"):
            current_user.clear()
            current_user.update({"id": member_id, "chapter_id": chapter_id, "role": role})
            return client

    return Harness()


@pytest.fixture
def make_supervisor(cursor, chapter_id):
    def _make(event_id: str, member_id: str, *, is_creator: bool = False) -> None:
        cursor.execute(
            "INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (chapter_id, event_id, member_id, is_creator),
        )

    return _make


@pytest.fixture
def make_organizer(cursor, chapter_id):
    def _make(event_id: str, member_id: str) -> None:
        cursor.execute(
            "INSERT INTO event_organizers (chapter_id, event_id, member_id, source) "
            "VALUES (%s, %s, %s, 'volunteer') ON CONFLICT DO NOTHING",
            (chapter_id, event_id, member_id),
        )

    return _make


@pytest.fixture
def security_job(cursor, chapter_id):
    def _make(event_id: str, *, status: str = "in_progress") -> str:
        cursor.execute(
            "INSERT INTO tasks (chapter_id, title, status, kind, event_id, people_needed) "
            "VALUES (%s, %s, %s, 'security', %s, 1) RETURNING id",
            (chapter_id, f"Security {uuid.uuid4().hex[:6]}", status, event_id),
        )
        return str(cursor.fetchone()["id"])

    return _make


def _task(cursor, task_id):
    cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    return cursor.fetchone()


def _audit_count(cursor, task_id, action):
    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs "
        "WHERE target_table = 'tasks' AND target_id = %s AND action = %s",
        (task_id, action),
    )
    return cursor.fetchone()["n"]


# ── edit: who may ────────────────────────────────────────────────────────────


def test_supervisor_edits_title_and_capacity(
    harness, cursor, chapter_id, member_factory, event_factory, task_factory, make_supervisor
):
    supervisor = member_factory()
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = task_factory(event_id=event_id, title="Setup", people_needed=1)

    resp = harness.login(supervisor, chapter_id).patch(
        f"/api/tasks/{task_id}", json={"title": "Setup the hall", "people_needed": 3}
    )
    assert resp.status_code == 200, resp.text

    row = _task(cursor, task_id)
    assert row["title"] == "Setup the hall"
    assert row["people_needed"] == 3
    assert row["status"] == "open"          # untouched
    assert str(row["event_id"]) == event_id  # parent untouched
    assert _audit_count(cursor, task_id, "UPDATE_TASK") == 1


def test_organizer_may_edit_but_a_stranger_may_not(
    harness, chapter_id, member_factory, event_factory, task_factory, make_organizer
):
    organizer, stranger = member_factory(), member_factory()
    event_id = event_factory(hours_from_now=72)
    make_organizer(event_id, organizer)
    task_id = task_factory(event_id=event_id)

    ok = harness.login(organizer, chapter_id).patch(
        f"/api/tasks/{task_id}", json={"description": "bring tape"}
    )
    assert ok.status_code == 200, ok.text

    denied = harness.login(stranger, chapter_id).patch(
        f"/api/tasks/{task_id}", json={"description": "nope"}
    )
    assert denied.status_code == 403, denied.text


def test_initiative_chair_may_edit_but_a_stranger_may_not(
    harness, chapter_id, member_factory, initiative_factory, task_factory
):
    chair, stranger = member_factory(), member_factory()
    initiative_id = initiative_factory(hours_from_now=72, chairs=[chair])
    task_id = task_factory(initiative_id=initiative_id)

    ok = harness.login(chair, chapter_id).patch(
        f"/api/tasks/{task_id}", json={"title": "Flyer run"}
    )
    assert ok.status_code == 200, ok.text

    denied = harness.login(stranger, chapter_id).patch(
        f"/api/tasks/{task_id}", json={"title": "Hijack"}
    )
    assert denied.status_code == 403, denied.text


# ── edit: guards ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["done_reported", "approved", "cancelled"])
def test_edit_after_reporting_is_409(
    harness, chapter_id, member_factory, event_factory, task_factory, make_supervisor, status
):
    supervisor = member_factory()
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = task_factory(event_id=event_id, status=status)

    resp = harness.login(supervisor, chapter_id).patch(
        f"/api/tasks/{task_id}", json={"title": "Too late"}
    )
    assert resp.status_code == 409, resp.text
    assert "job_not_editable" in resp.text


def test_capacity_may_not_drop_below_active_claims(
    harness, cursor, chapter_id, member_factory, event_factory, task_factory, make_supervisor
):
    supervisor = member_factory()
    claimants = [member_factory(), member_factory()]
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = task_factory(event_id=event_id, people_needed=2)
    for member in claimants:
        commit_task(cursor, chapter_id, task_id, member)

    resp = harness.login(supervisor, chapter_id).patch(
        f"/api/tasks/{task_id}", json={"people_needed": 1}
    )
    assert resp.status_code == 409, resp.text
    assert "job_capacity_below_claims" in resp.text
    assert _task(cursor, task_id)["people_needed"] == 2


def test_security_job_cannot_be_edited(
    harness, chapter_id, member_factory, event_factory, security_job, make_supervisor
):
    supervisor = member_factory()
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = security_job(event_id)

    resp = harness.login(supervisor, chapter_id).patch(
        f"/api/tasks/{task_id}", json={"title": "Reassign"}
    )
    assert resp.status_code == 409, resp.text
    assert "security_no_edit" in resp.text


def test_parent_fields_in_the_body_are_ignored(
    harness, cursor, chapter_id, member_factory, event_factory, task_factory, make_supervisor
):
    supervisor = member_factory()
    event_id, other_event_id = event_factory(hours_from_now=72), event_factory(hours_from_now=96)
    make_supervisor(event_id, supervisor)
    task_id = task_factory(event_id=event_id)

    resp = harness.login(supervisor, chapter_id).patch(
        f"/api/tasks/{task_id}",
        json={"title": "Still mine", "event_id": other_event_id, "status": "approved"},
    )
    assert resp.status_code == 200, resp.text
    row = _task(cursor, task_id)
    assert str(row["event_id"]) == event_id
    assert row["status"] == "open"


def test_empty_patch_is_422(
    harness, chapter_id, member_factory, event_factory, task_factory, make_supervisor
):
    supervisor = member_factory()
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = task_factory(event_id=event_id)

    resp = harness.login(supervisor, chapter_id).patch(f"/api/tasks/{task_id}", json={})
    assert resp.status_code == 422, resp.text


# ── cancel ───────────────────────────────────────────────────────────────────


def test_delete_open_job_cancels_it_and_drops_the_job_count(
    harness, cursor, chapter_id, sb_client, member_factory, event_factory,
    task_factory, make_supervisor,
):
    from api.events.services.events import _job_counts_for_event

    supervisor = member_factory()
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = task_factory(event_id=event_id)
    assert _job_counts_for_event(sb_client, event_id) == (1, 1)

    resp = harness.login(supervisor, chapter_id).delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 200, resp.text

    row = _task(cursor, task_id)
    assert row is not None and row["status"] == "cancelled"  # never a hard delete
    assert _audit_count(cursor, task_id, "CANCEL_TASK") == 1
    assert _job_counts_for_event(sb_client, event_id) == (0, 0)


def test_delete_claimed_job_is_409(
    harness, cursor, chapter_id, member_factory, event_factory, task_factory, make_supervisor
):
    supervisor, claimant = member_factory(), member_factory()
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = task_factory(event_id=event_id)
    commit_task(cursor, chapter_id, task_id, claimant)  # open → in_progress

    resp = harness.login(supervisor, chapter_id).delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 409, resp.text
    assert "job_not_cancellable" in resp.text
    assert _task(cursor, task_id)["status"] == "in_progress"


def test_delete_security_job_is_409(
    harness, chapter_id, member_factory, event_factory, security_job, make_supervisor
):
    supervisor = member_factory()
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = security_job(event_id, status="open")

    resp = harness.login(supervisor, chapter_id).delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 409, resp.text
    assert "security_no_cancel" in resp.text


def test_cancel_replays_on_the_same_idempotency_key(
    harness, cursor, chapter_id, member_factory, event_factory, task_factory, make_supervisor
):
    supervisor = member_factory()
    event_id = event_factory(hours_from_now=72)
    make_supervisor(event_id, supervisor)
    task_id = task_factory(event_id=event_id)
    client = harness.login(supervisor, chapter_id)
    key = {"Idempotency-Key": str(uuid.uuid4())}

    first = client.delete(f"/api/tasks/{task_id}", headers=key)
    assert first.status_code == 200, first.text
    second = client.delete(f"/api/tasks/{task_id}", headers=key)
    assert second.status_code == 200, second.text
    assert second.json() == first.json()          # the replay, not a second cancel
    assert _audit_count(cursor, task_id, "CANCEL_TASK") == 1
