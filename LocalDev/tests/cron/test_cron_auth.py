"""CRON_SECRET gate on every cron route (GTMLarpChecklist 3.6).

DB-free by construction: 401s are raised by the dependency before any handler
runs, and the one authorized case stubs the drain service out. Only the app
import (FastAPI) is required.
"""

from __future__ import annotations

import pytest

CRON_ROUTES = ["/api/cron/process-fines", "/api/cron/drain-outbox"]


@pytest.fixture
def client(monkeypatch):
    """TestClient with a configured secret and the drain service stubbed out."""
    from fastapi.testclient import TestClient

    import api.cron.api.cron as cron_api
    from api.config import settings

    monkeypatch.setattr(settings, "CRON_SECRET", "test-cron-secret")
    monkeypatch.setattr(
        cron_api,
        "drain_outbox",
        lambda: {"processed": 0, "sent": 0, "simulated": 0, "failed": 0},
    )

    from api.index import app

    return TestClient(app)


@pytest.fixture
def no_secret(monkeypatch):
    from api.config import settings

    monkeypatch.setattr(settings, "CRON_SECRET", "")


BEARER = {"Authorization": "Bearer test-cron-secret"}


# ── Rejection ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", CRON_ROUTES)
def test_no_authorization_header_is_401(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", CRON_ROUTES)
def test_wrong_secret_is_401(client, path):
    resp = client.get(path, headers={"Authorization": "Bearer wrong-secret"})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", CRON_ROUTES)
def test_bare_secret_without_the_bearer_scheme_is_401(client, path):
    resp = client.get(path, headers={"Authorization": "test-cron-secret"})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", CRON_ROUTES)
def test_unconfigured_secret_disables_the_route_entirely(client, no_secret, path):
    """Empty CRON_SECRET means 401 for everyone — including an empty header.

    An unconfigured deploy must not have triggerable cron endpoints.
    """
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer"}).status_code == 401
    assert client.get(path, headers={"Authorization": ""}).status_code == 401


def test_post_drain_outbox_is_also_gated(client):
    assert client.post("/api/cron/drain-outbox").status_code == 401


# ── Acceptance ───────────────────────────────────────────────────────────────


def test_correct_bearer_secret_is_accepted(client):
    resp = client.get("/api/cron/process-fines", headers=BEARER)
    assert resp.status_code == 200
    # The disabled response body is unchanged by the auth work.
    assert resp.json() == {
        "status": "disabled",
        "reason": "V1: fines are never automatic; use POST /api/fines/issue",
    }


def test_drain_outbox_accepts_get_the_way_vercel_cron_calls_it(client):
    """Vercel Cron issues GET with `Authorization: Bearer $CRON_SECRET`."""
    resp = client.get("/api/cron/drain-outbox", headers=BEARER)
    assert resp.status_code == 200
    assert set(resp.json()) == {"processed", "sent", "simulated", "failed"}


def test_drain_outbox_also_accepts_post_for_manual_ops(client):
    resp = client.post("/api/cron/drain-outbox", headers=BEARER)
    assert resp.status_code == 200
    assert set(resp.json()) == {"processed", "sent", "simulated", "failed"}
