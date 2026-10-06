"""Security and supervisor guard failures have fixed client responses."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.dependencies import get_current_user
from api.events.api import security, events


@pytest.mark.parametrize("module,service,path,body,fragment,status,detail", [
    (security, "assign_security", "/event/security", {"member_id": "member"}, "target_already_assigned", 409, "target_already_assigned"),
    (security, "assign_security", "/event/security", {"member_id": "member"}, "member private is not an active member", 422, "Member must be active"),
    (events, "add_supervisor", "/event/supervisors", {"member_id": "member"}, "member private is not an active member", 422, "Member must be active"),
    (events, "create_event", "/", {"title": "Event", "date": "2026-10-07", "time": "12:00", "location": "Hall"}, "member private is not an active member", 422, "Member must be active"),
])
def test_event_guard_messages(monkeypatch, module, service, path, body, fragment, status, detail):
    monkeypatch.setattr(module, "get_db", lambda: object())
    def fail(*a, **kw):
        raise RuntimeError(fragment + " SQLSTATE XX000 relation private DETAIL secret")
    monkeypatch.setattr(module.svc, service, fail)
    app = FastAPI()
    app.include_router(module.router)
    for route in module.router.routes:
        for dependency in route.dependant.dependencies:
            app.dependency_overrides[dependency.call] = lambda: {"id": "actor", "chapter_id": "chapter"}
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(path, json=body)
    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_unknown_security_error_is_generic_500(monkeypatch):
    monkeypatch.setattr(security, "get_db", lambda: object())
    def fail(*a, **kw):
        raise RuntimeError("SQLSTATE XX000 relation private DETAIL secret")
    monkeypatch.setattr(security.svc, "assign_security", fail)
    app = FastAPI()
    app.include_router(security.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "actor", "chapter_id": "chapter"}
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/event/security", json={"member_id": "member"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
