"""RPC errors must expose only fixed HTTP messages."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.dependencies import get_current_user
from api.tasks.api import commitments, jobs, tasks


@pytest.mark.parametrize("module,service,path,method,body,fragment,status,detail", [
    (commitments, "commit_task", "/task/commit", "post", {}, "task private not found", 404, "Task or member not found"),
    (commitments, "commit_task", "/task/commit", "post", {}, "job_full", 409, "job_full"),
    (commitments, "commit_task", "/task/commit", "post", {}, "member x has no active commitment on task y", 409, "Member has no active commitment on this task"),
    (commitments, "commit_task", "/task/commit", "post", {}, "member already has an active commitment", 409, "Member already has an active commitment"),
    (jobs, "approve_task", "/task/approve", "post", None, "cannot be approved", 409, "Job cannot be approved"),
    (tasks, "update_task", "/task", "patch", {"title": "Updated"}, "job_title_required", 422, "A job title is required"),
    (tasks, "update_task", "/task", "patch", {"title": "Updated"}, "security_no_status_change", 400, "security_no_status_change"),
])
@pytest.mark.parametrize("unknown", [False, True])
def test_rpc_route_messages(monkeypatch, module, service, path, method, body, fragment, status, detail, unknown):
    monkeypatch.setattr(module, "get_db", lambda: object())
    if module is jobs:
        monkeypatch.setattr(jobs, "_load_task_or_404", lambda *a, **kw: {})
        monkeypatch.setattr(jobs, "can_approve_job", lambda *a, **kw: True)
    if module is tasks:
        monkeypatch.setattr(tasks, "_manageable_task_or_error", lambda *a, **kw: {})
    def fail(*a, **kw):
        raise RuntimeError(("database unavailable" if unknown else fragment) + " SQLSTATE XX000 relation private DETAIL secret")
    monkeypatch.setattr(module.svc, service, fail)
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "actor", "chapter_id": "chapter"}
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == (500 if unknown else status)
    assert response.json() == {"detail": "Internal server error" if unknown else detail}


@pytest.mark.parametrize("mapper", [tasks._rpc_http_error, jobs._rpc_http_error])
def test_unknown_rpc_error_is_generic_server_error(mapper):
    result = mapper(RuntimeError("SQLSTATE XX000 relation private DETAIL secret"))
    assert result.status_code == 500
    assert result.detail == "Internal server error"


@pytest.mark.parametrize("fragment,detail", [
    ("task_closed:", "A closed task cannot change status"),
    ("task_in_review:", "Please approve or reject the reported job"),
    ("job_needs_review:", "Jobs are completed through report and approve"),
])
def test_status_guard_never_echoes_database_suffix(monkeypatch, fragment, detail):
    from types import SimpleNamespace
    class Query:
        def select(self, *a): return self
        def eq(self, *a): return self
        def execute(self): return SimpleNamespace(data=[])
    monkeypatch.setattr(tasks, "get_db", lambda: SimpleNamespace(table=lambda name: Query()))
    monkeypatch.setattr(tasks.svc, "get_task", lambda *a, **kw: {"assigned_member_id": "actor"})
    monkeypatch.setattr(tasks, "has_permission", lambda *a, **kw: True)
    def fail(*a, **kw):
        raise RuntimeError(fragment + " SQLSTATE XX000 relation private DETAIL secret")
    monkeypatch.setattr(tasks.svc, "update_task_status", fail)
    app = FastAPI()
    app.include_router(tasks.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "actor", "chapter_id": "chapter"}
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/task/status", json={"status": "done"})
    assert response.status_code == 409
    assert response.json() == {"detail": detail}
