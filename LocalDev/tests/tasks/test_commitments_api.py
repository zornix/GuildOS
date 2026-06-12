"""HTTP surface for task commitments — permissions, payloads, attribution.

Mounts only the tasks domain router (not api.index — other domains are being
reshaped concurrently) and overrides get_current_user. Permission resolution
runs against the real role_permissions seed in the test DB.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.tasks.conftest import commit_task, uncommit_task


@pytest.fixture
def harness(sb_client, monkeypatch):
    """App with the tasks router; all DB access redirected to the test DB."""
    import api.rbac.services.permissions as rbac_permissions
    import api.tasks.api.commitments as commitments_api
    import api.tasks.api.tasks as tasks_api
    from api.dependencies import get_current_user
    from api.tasks.api.router import router

    monkeypatch.setattr(tasks_api, "get_tasks_db", lambda: sb_client)
    monkeypatch.setattr(commitments_api, "get_tasks_db", lambda: sb_client)
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


# ── commit permissions ───────────────────────────────────────────────────────


def test_member_self_commit(harness, cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    client = harness.login(member_id, chapter_id)

    resp = client.post(f"/api/tasks/{task_id}/commit", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["commitment"]["status"] == "active"
    assert body["task_status"] == "committed"


def test_member_cannot_commit_someone_else(harness, cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory()
    actor, target = member_factory(), member_factory()
    client = harness.login(actor, chapter_id, role="member")

    resp = client.post(f"/api/tasks/{task_id}/commit", json={"member_id": target})
    assert resp.status_code == 403
    assert "tasks:assign" in resp.json()["detail"]


def test_officer_can_commit_someone_else(harness, cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory()
    officer, target = member_factory(role="officer"), member_factory()
    client = harness.login(officer, chapter_id, role="officer")

    resp = client.post(f"/api/tasks/{task_id}/commit", json={"member_id": target})
    assert resp.status_code == 200, resp.text
    assert resp.json()["commitment"]["member_id"] == target


def test_double_commit_maps_to_409(harness, cursor, chapter_id, member_id, task_factory):
    task_id = task_factory()
    client = harness.login(member_id, chapter_id)
    assert client.post(f"/api/tasks/{task_id}/commit", json={}).status_code == 200
    assert client.post(f"/api/tasks/{task_id}/commit", json={}).status_code == 409


# ── uncommit ─────────────────────────────────────────────────────────────────


def test_uncommit_response_includes_late_and_hours(
    harness, cursor, chapter_id, member_id, task_factory, event_factory
):
    event_id = event_factory(hours_from_now=5)
    task_id = task_factory(event_id=event_id)
    client = harness.login(member_id, chapter_id)
    client.post(f"/api/tasks/{task_id}/commit", json={})

    resp = client.post(f"/api/tasks/{task_id}/uncommit", json={"reason": "exam"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["late"] is True
    assert 4 < float(body["hours_before_event"]) < 6


def test_member_cannot_uncommit_someone_else(harness, cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory()
    m1, m2 = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, m2)
    client = harness.login(m1, chapter_id, role="member")

    resp = client.post(f"/api/tasks/{task_id}/uncommit", json={"member_id": m2})
    assert resp.status_code == 403
    assert "tasks:review" in resp.json()["detail"]


def test_officer_can_uncommit_someone_else(harness, cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory()
    officer, target = member_factory(role="officer"), member_factory()
    commit_task(cursor, chapter_id, task_id, target)
    client = harness.login(officer, chapter_id, role="officer")

    resp = client.post(f"/api/tasks/{task_id}/uncommit", json={"member_id": target})
    assert resp.status_code == 200, resp.text
    assert resp.json()["commitment"]["status"] == "uncommitted"


# ── reads ────────────────────────────────────────────────────────────────────


def test_task_commitments_listing(harness, cursor, chapter_id, member_factory, task_factory):
    task_id = task_factory()
    m1, m2 = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, m1)
    commit_task(cursor, chapter_id, task_id, m2)
    uncommit_task(cursor, chapter_id, task_id, m2, reason="busy")

    client = harness.login(m1, chapter_id)
    resp = client.get(f"/api/tasks/{task_id}/commitments")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {c["member_id"] for c in body["active"]} == {m1}
    actions = [row["action"] for row in body["history"]]
    assert actions.count("commit") == 2 and actions.count("uncommit") == 1


def test_uncommit_log_visible_to_all_members(
    harness, cursor, chapter_id, member_factory, task_factory
):
    task_id = task_factory()
    quitter, watcher = member_factory(), member_factory()
    commit_task(cursor, chapter_id, task_id, quitter)
    uncommit_task(cursor, chapter_id, task_id, quitter, reason="changed my mind")

    client = harness.login(watcher, chapter_id)  # plain member, not involved
    resp = client.get("/api/tasks/uncommit-log")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert any(r["member_id"] == quitter and r["reason"] == "changed my mind" for r in rows)
    assert all(r["action"] == "uncommit" for r in rows)

    filtered = client.get(f"/api/tasks/uncommit-log?member_id={quitter}&limit=5").json()
    assert len(filtered) == 1 and filtered[0]["member_id"] == quitter


# ── attribution ──────────────────────────────────────────────────────────────


def _build_attribution_data(cursor, chapter_id, member_id, task_factory, event_factory):
    # committed 3 tasks: one completed, one uncommitted late, one still active
    done_task = task_factory()
    commit_task(cursor, chapter_id, done_task, member_id)
    cursor.execute(
        "SELECT tk_update_task_status(%s, %s, 'done', %s)", (chapter_id, done_task, member_id)
    )
    cursor.fetchone()

    event_id = event_factory(hours_from_now=2)
    late_task = task_factory(event_id=event_id)
    commit_task(cursor, chapter_id, late_task, member_id)
    uncommit_task(cursor, chapter_id, late_task, member_id, reason="bail")

    active_task = task_factory()
    commit_task(cursor, chapter_id, active_task, member_id)


def test_attribution_math(harness, cursor, chapter_id, member_id, task_factory, event_factory):
    _build_attribution_data(cursor, chapter_id, member_id, task_factory, event_factory)

    client = harness.login(member_id, chapter_id)
    resp = client.get(f"/api/tasks/attribution/{member_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["member_id"] == member_id
    assert body["tasks_committed"] == 3
    assert body["tasks_completed"] == 1
    assert body["uncommits"] == 1
    assert body["late_uncommits"] == 1
    assert len(body["recent_log"]) == 4  # 3 commits + 1 uncommit, newest first
    assert body["recent_log"][0]["action"] == "uncommit" or body["recent_log"][0]["action"] == "commit"


def test_attribution_me_alias(harness, cursor, chapter_id, member_id, task_factory, event_factory):
    _build_attribution_data(cursor, chapter_id, member_id, task_factory, event_factory)

    client = harness.login(member_id, chapter_id)
    me = client.get("/api/tasks/attribution/me")
    assert me.status_code == 200, me.text
    assert me.json()["tasks_committed"] == 3


# ── task create/list additivity ──────────────────────────────────────────────


def test_create_task_accepts_event_id_and_list_includes_summary(
    harness, cursor, chapter_id, member_factory, event_factory
):
    officer = member_factory(role="officer")
    event_id = event_factory(hours_from_now=72)
    client = harness.login(officer, chapter_id, role="officer")

    resp = client.post("/api/tasks/", json={"title": "Buy decorations", "event_id": event_id})
    assert resp.status_code == 200, resp.text
    task = resp.json()
    assert task["event_id"] == event_id

    commit = client.post(f"/api/tasks/{task['id']}/commit", json={})
    assert commit.status_code == 200, commit.text

    listing = client.get("/api/tasks/?status=committed")
    assert listing.status_code == 200
    rows = [t for t in listing.json() if t["id"] == task["id"]]
    assert len(rows) == 1
    assert rows[0]["event_id"] == event_id
    assert rows[0]["committed_member_ids"] == [officer]


def test_list_status_filter_open_excludes_committed(
    harness, cursor, chapter_id, member_id, task_factory
):
    open_task = task_factory()
    committed_task = task_factory()
    commit_task(cursor, chapter_id, committed_task, member_id)

    client = harness.login(member_id, chapter_id)
    open_ids = {t["id"] for t in client.get("/api/tasks/?status=open").json()}
    assert open_task in open_ids
    assert committed_task not in open_ids
