"""Health response contract against the demo client and a failed ping."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from api.health_checks import build_health_payload
from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.mark.parametrize("age,status,check", [(0,"ok","ok"), (30,"degraded","stale"), (None,"ok","unknown")])
def test_health_reports_heartbeat(sb_client, age, status, check):
    class Rollback(Exception):
        pass

    try:
        with sb_client.transaction() as tx:
            if age is None:
                tx.table("cron_heartbeats").delete().eq("job", "drain-outbox").execute()
            else:
                timestamp = (datetime.now(timezone.utc)-timedelta(minutes=age)).isoformat()
                tx.table("cron_heartbeats").upsert({"job":"drain-outbox", "last_started_at":timestamp, "last_finished_at":timestamp, "last_counts":{}}, on_conflict="job").execute()
            payload = build_health_payload(tx)
            assert payload["status"] == status
            assert payload["checks"] == {"database":"ok", "outbox_drain":check}
            raise Rollback
    except Rollback:
        pass


def test_health_handler_returns_503_when_database_is_down(monkeypatch):
    import api.index as index

    class Unreachable:
        def ping(self):
            raise RuntimeError("unreachable")

        def table(self, name):
            pytest.fail("heartbeat must not be checked when ping fails")

    monkeypatch.setattr(index, "get_db", lambda: Unreachable())
    response = TestClient(index.app).get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status":"error", "version":"0.1.0", "checks":{"database":"error"}, "detail":"database_unreachable"}


def test_health_missing_heartbeat_table_is_unknown(sb_client):
    class MissingHeartbeat:
        ping = sb_client.ping

        def table(self, name):
            raise RuntimeError("table unavailable")

    payload = build_health_payload(MissingHeartbeat())
    assert payload["status"] == "ok"
    assert payload["checks"] == {"database":"ok", "outbox_drain":"unknown"}
