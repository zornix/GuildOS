"""Exercise RPC guard mapping through initiative routes and the real service."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.dependencies import get_current_user
from api.initiatives.api import initiatives as routes
from api.initiatives.services import initiatives as svc


@pytest.mark.parametrize("method,path,body,error,status,detail", [
    ("delete", "/initiative/chairs/member", None, "member private is not a chair", 404, "Member not found"),
    ("post", "/initiative/chairs", {"member_id": "member"}, "member private is not an active member", 422, "Member must be active"),
    ("post", "/", {"title": "Initiative", "date": "2026-10-07", "time": "12:00"}, "member private is not an active member", 422, "Member must be active"),
])
def test_initiative_guard_messages(monkeypatch, method, path, body, error, status, detail):
    monkeypatch.setattr(routes, "get_db", lambda: object())
    monkeypatch.setattr(svc, "_get_initiative_row", lambda *a, **kw: {})
    monkeypatch.setattr(svc, "is_assigned_chair", lambda *a, **kw: True)
    def fail(*a, **kw):
        raise RuntimeError(error + " SQLSTATE XX000 relation private DETAIL secret")
    monkeypatch.setattr(svc, "call_rpc", fail)
    app = FastAPI()
    app.include_router(routes.router)
    for route in routes.router.routes:
        for dependency in route.dependant.dependencies:
            app.dependency_overrides[dependency.call] = lambda: {"id": "actor", "chapter_id": "chapter"}
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.request(method, path, json=body)
    assert response.status_code == status
    assert response.json() == {"detail": detail}
