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
    pending_queries = []

    class ScopedHeartbeatClient:
        def table(self, name):
            query = heartbeat_client.table(name)
            if name == "message_outbox":
                class PendingTable:
                    def select(self, *args, **kwargs):
                        selected = query.select(*args, **kwargs).eq("chapter_id", chapter_id)
                        pending_queries.append(selected)
                        return selected
                return PendingTable()
            return query

    mod.drain_outbox(ScopedHeartbeatClient())
    assert pending_queries
    assert all(("eq", "chapter_id", chapter_id) in query._filters for query in pending_queries)
    heartbeat = heartbeat_client.table("cron_heartbeats").select("*").eq("job", "drain-outbox").single().execute().data
    assert 600 <= heartbeat["oldest_pending_seconds"] < 660


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


def test_budget_release_db_error_does_not_fail_route_or_skip_heartbeat(
    heartbeat_client, cron_client, auth_header, outbox_row,
    chapter_id, monkeypatch,
):
    from types import SimpleNamespace
    from api.cron.services import outbox_drain as mod
    from api.platform.postgres import QueryBuilder

    for _ in range(3):
        outbox_row()
    claimed = heartbeat_client.rpc("outbox_claim_batch", {"p_limit": 3, "p_chapter_id": chapter_id}).execute().data
    clock = [0]
    monkeypatch.setattr(mod, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(mod, "_resolve_sb", lambda sb=None: heartbeat_client)
    monkeypatch.setattr(mod, "call_rpc", lambda *a, **kw: SimpleNamespace(data=claimed))

    def consume_budget(*args, **kwargs):
        clock[0] = mod.DRAIN_BUDGET_SECONDS + 1
        return "simulated"

    execute = QueryBuilder.execute
    release_attempts = []

    def fail_first_release(query):
        if query._table == "message_outbox" and query._op == "update" and query._payload.get("status") == "pending":
            release_attempts.append(query)
            if len(release_attempts) == 1:
                raise RuntimeError("database unavailable")
        return execute(query)

    monkeypatch.setattr(mod, "_deliver_row", consume_budget)
    monkeypatch.setattr(QueryBuilder, "execute", fail_first_release)
    response = cron_client.get("/api/cron/drain-outbox", headers=auth_header())
    assert response.status_code == 200
    assert len(release_attempts) == 2
    failed_release = heartbeat_client.table("message_outbox").select("*").eq("id", claimed[1]["id"]).single().execute().data
    assert failed_release["status"] == "sending"
    released = heartbeat_client.table("message_outbox").select("*").eq("id", claimed[2]["id"]).single().execute().data
    assert released["status"] == "pending"
    assert released["attempts"] == 0
    heartbeat = heartbeat_client.table("cron_heartbeats").select("*").eq("job", "drain-outbox").single().execute().data
    assert heartbeat["last_counts"]["processed"] == 1
    assert (datetime.now(timezone.utc) - heartbeat["last_finished_at"]).total_seconds() < 60
