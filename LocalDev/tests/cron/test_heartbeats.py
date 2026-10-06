"""Scheduled drain heartbeats use a rolled-back connection on the demo DB."""
from datetime import datetime, timezone

import pytest


@pytest.fixture
def heartbeat_client(sb_client):
    class Rollback(Exception):
        pass

    try:
        with sb_client.transaction() as tx:
            yield tx
            raise Rollback
    except Rollback:
        pass


def test_drain_records_a_heartbeat_even_when_idle(
    heartbeat_client, cron_client, auth_header, monkeypatch
):
    from api.cron.services import outbox_drain as mod
    monkeypatch.setattr(mod, "_resolve_sb", lambda sb=None: heartbeat_client)
    from types import SimpleNamespace
    monkeypatch.setattr(mod, "call_rpc", lambda *a, **kw: SimpleNamespace(data=[]))
    response = cron_client.get("/api/cron/drain-outbox", headers=auth_header())
    assert response.status_code == 200
    row = heartbeat_client.table("cron_heartbeats").select("*").eq("job", "drain-outbox").single().execute().data
    assert row["last_counts"]["processed"] == 0
    assert (datetime.now(timezone.utc) - row["last_finished_at"]).total_seconds() < 60


def test_heartbeat_reports_oldest_pending_age(
    heartbeat_client, outbox_row, chapter_id, cursor, monkeypatch
):
    from api.cron.services import outbox_drain as mod
    row = outbox_row()
    cursor.execute("UPDATE message_outbox SET created_at=now()-interval '10 minutes' WHERE id=%s AND chapter_id=%s", (row["id"], chapter_id))
    monkeypatch.setattr(mod, "DRAIN_BUDGET_SECONDS", 0)
    mod.drain_outbox(heartbeat_client)
    heartbeat = heartbeat_client.table("cron_heartbeats").select("*").eq("job", "drain-outbox").single().execute().data
    assert heartbeat["oldest_pending_seconds"] >= 600


def test_chapter_scoped_drain_writes_no_heartbeat(
    heartbeat_client, chapter_id, monkeypatch
):
    from api.cron.services import outbox_drain as mod
    heartbeat_client.table("cron_heartbeats").delete().eq("job", "drain-outbox").execute()
    monkeypatch.setattr(mod, "DRAIN_BUDGET_SECONDS", 0)
    mod.drain_outbox(heartbeat_client, chapter_id=chapter_id)
    assert heartbeat_client.table("cron_heartbeats").select("*").eq("job", "drain-outbox").execute().data == []


def test_drain_routes_have_unique_operation_ids(cron_client):
    schema = cron_client.app.openapi()
    path = schema["paths"]["/api/cron/drain-outbox"]
    assert path["get"]["operationId"] != path["post"]["operationId"]
