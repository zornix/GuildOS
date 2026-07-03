"""HTTP surface for job lifecycle (report-done/approve/reject) and the
create/commit permission gates around it (docs/imp-ev-ph2.md section 5.3,
Phase 1 follow-up).

Mounts only the tasks domain router (mirrors tests/tasks/test_commitments_api.py's
harness), extended to also patch api.tasks.api.jobs.get_tasks_db (the Phase 1
review found jobs.py had no HTTP coverage at all).
"""

from __future__ import annotations

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

    monkeypatch.setattr(tasks_api, "get_tasks_db", lambda: sb_client)
    monkeypatch.setattr(commitments_api, "get_tasks_db", lambda: sb_client)
    monkeypatch.setattr(jobs_api, "get_tasks_db", lambda: sb_client)
    monkeypatch.setattr(rbac_permissions, "get_rbac_db", lambda: sb_client)

    app = FastAPI()
    app.include_router(router, prefix="/api/tasks")

    current_user: dict = {}
    app.dependency_overrides[get_current_user] = lambda: current_user

    client = TestClient(app)

    class Harness:
        def __init__(self):
            self.client = client

        def login(self, member_id: str, chapter_id: str, role: str = "member"):
            current_user.clear()
            current_user.update({"id": member_id, "chapter_id": chapter_id, "role": role})
            return client

    return Harness()


@pytest.fixture
def assign_role(cursor, chapter_id):
    """Insert a member_roles row directly (test shortcut; prod uses rbac_assign_role)."""

    def _assign(member_id: str, role_key: str, *, chapter: str | None = None) -> None:
        cursor.execute(
            """
            INSERT INTO member_roles (chapter_id, member_id, role_key)
            VALUES (%s, %s, %s)
            ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING
            """,
            (chapter or chapter_id, member_id, role_key),
        )

    return _assign


# ── report-done ──────────────────────────────────────────────────────────


def test_report_done_by_non_claimant_is_403(harness, cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory()
    claimant, other = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, claimant)

    client = harness.login(other, chapter_id)
    resp = client.post(f"/api/tasks/{task_id}/report-done")
    assert resp.status_code == 403


def test_second_report_done_is_409(harness, cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    client = harness.login(member_id, chapter_id)

    first = client.post(f"/api/tasks/{task_id}/report-done")
    assert first.status_code == 200, first.text
    second = client.post(f"/api/tasks/{task_id}/report-done")
    assert second.status_code == 409


# ── reject reason validation ─────────────────────────────────────────────


def test_reject_blank_reason_is_422(
    harness, cursor, chapter_id, member_id, member_factory, task_factory
):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    assert harness.login(member_id, chapter_id).post(f"/api/tasks/{task_id}/report-done").status_code == 200

    officer = member_factory(role="officer")
    client = harness.login(officer, chapter_id, role="officer")
    resp = client.post(f"/api/tasks/{task_id}/reject", json={"reason": ""})
    assert resp.status_code == 422


def test_reject_whitespace_only_reason_is_422(
    harness, cursor, chapter_id, member_id, member_factory, task_factory
):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    assert harness.login(member_id, chapter_id).post(f"/api/tasks/{task_id}/report-done").status_code == 200

    officer = member_factory(role="officer")
    client = harness.login(officer, chapter_id, role="officer")
    resp = client.post(f"/api/tasks/{task_id}/reject", json={"reason": "   "})
    assert resp.status_code == 422


# ── approve/reject permissions ───────────────────────────────────────────


def test_approve_standalone_job_by_plain_member_is_403(
    harness, cursor, chapter_id, member_id, member_factory, task_factory
):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    assert harness.login(member_id, chapter_id).post(f"/api/tasks/{task_id}/report-done").status_code == 200

    plain = member_factory()
    client = harness.login(plain, chapter_id, role="member")
    resp = client.post(f"/api/tasks/{task_id}/approve")
    assert resp.status_code == 403


def test_reject_standalone_job_by_plain_member_is_403(
    harness, cursor, chapter_id, member_id, member_factory, task_factory
):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    assert harness.login(member_id, chapter_id).post(f"/api/tasks/{task_id}/report-done").status_code == 200

    plain = member_factory()
    client = harness.login(plain, chapter_id, role="member")
    resp = client.post(f"/api/tasks/{task_id}/reject", json={"reason": "not actually done"})
    assert resp.status_code == 403


def test_approve_standalone_job_by_tasks_review_holder_is_200(
    harness, cursor, chapter_id, member_id, member_factory, task_factory
):
    task_id = task_factory()
    commit_task(cursor, chapter_id, task_id, member_id)
    assert harness.login(member_id, chapter_id).post(f"/api/tasks/{task_id}/report-done").status_code == 200

    officer = member_factory(role="officer")  # officer role holds tasks:review
    client = harness.login(officer, chapter_id, role="officer")
    resp = client.post(f"/api/tasks/{task_id}/approve")
    assert resp.status_code == 200, resp.text


# ── job_full (commitments.py) ────────────────────────────────────────────


def test_commit_when_job_full_is_409(harness, cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory(people_needed=1)
    m1, m2 = member_factory(), member_factory()

    first = harness.login(m1, chapter_id).post(f"/api/tasks/{task_id}/commit", json={})
    assert first.status_code == 200, first.text

    resp = harness.login(m2, chapter_id).post(f"/api/tasks/{task_id}/commit", json={})
    assert resp.status_code == 409
    assert "job_full" in resp.json()["detail"]


# ── job-create-on-event permission gate ─────────────────────────────────


def test_create_event_job_without_supervisor_organizer_or_tasks_assign_is_403(
    harness, cursor, chapter_id, member_factory, event_factory, assign_role
):
    event_id = event_factory(hours_from_now=72)
    actor = member_factory()
    assign_role(actor, "recruitment_chair")  # holds tasks:create, lacks tasks:assign

    client = harness.login(actor, chapter_id, role="member")
    resp = client.post("/api/tasks/", json={"title": "Order decorations", "event_id": event_id})
    assert resp.status_code == 403
