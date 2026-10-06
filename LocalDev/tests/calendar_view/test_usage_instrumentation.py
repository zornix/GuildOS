"""Instrumentation (spec build-order #6): /api/usage track + summary, and the
server-side calendar:viewed tracking hook."""

from __future__ import annotations

import psycopg2
import pytest


def _usage_rows(cursor, chapter_id, event_name=None):
    if event_name:
        cursor.execute(
            "SELECT * FROM usage_events WHERE chapter_id = %s AND event_name = %s",
            (chapter_id, event_name),
        )
    else:
        cursor.execute("SELECT * FROM usage_events WHERE chapter_id = %s", (chapter_id,))
    return cursor.fetchall()


# ── POST /api/usage/track ────────────────────────────────────────────────────


def test_track_inserts_row(harness, cursor, chapter_id, user_factory):
    user = user_factory()
    resp = harness.login(user).post(
        "/api/usage/track",
        json={"event_name": "tab:opened", "metadata": {"tab": "treasury"}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True}

    rows = _usage_rows(cursor, chapter_id, "tab:opened")
    assert len(rows) == 1
    assert str(rows[0]["member_id"]) == user["id"]
    assert rows[0]["metadata"] == {"tab": "treasury"}


def test_track_drops_bad_names_and_truncates_metadata(harness, cursor, chapter_id, user_factory):
    """D13: a name outside the strict pattern is dropped silently; big metadata is truncated."""
    user = user_factory()
    client = harness.login(user)
    resp = client.post("/api/usage/track", json={"event_name": "x" * 500, "metadata": {}})
    assert resp.status_code == 200, resp.text
    assert _usage_rows(cursor, chapter_id) == []

    resp = client.post(
        "/api/usage/track",
        json={"event_name": "tab:opened", "metadata": {"blob": "y" * 20000}},
    )
    assert resp.status_code == 200, resp.text
    rows = _usage_rows(cursor, chapter_id)
    assert len(rows) == 1
    assert rows[0]["metadata"] == {"_truncated": True}


def test_track_requires_event_name(harness, user_factory):
    resp = harness.login(user_factory()).post("/api/usage/track", json={"metadata": {}})
    assert resp.status_code == 422


def test_usage_events_cannot_be_updated_but_can_be_deleted(harness, cursor, chapter_id, user_factory):
    """D13: rows are immutable but deletable (retention, member cascade)."""
    harness.login(user_factory()).post("/api/usage/track", json={"event_name": "e1"})
    row_id = _usage_rows(cursor, chapter_id, "e1")[0]["id"]

    with pytest.raises(psycopg2.Error, match="append-only"):
        cursor.execute("UPDATE usage_events SET event_name = 'tampered' WHERE id = %s", (row_id,))
    cursor.execute("DELETE FROM usage_events WHERE id = %s", (row_id,))
    assert _usage_rows(cursor, chapter_id, "e1") == []


# ── GET /api/usage/summary ───────────────────────────────────────────────────


def test_summary_gated_to_officers(harness, user_factory):
    plain = user_factory()
    resp = harness.login(plain).get("/api/usage/summary")
    assert resp.status_code == 403

    officer = user_factory(role="officer")  # legacy role → calendar:officer:view
    resp = harness.login(officer).get("/api/usage/summary")
    assert resp.status_code == 200, resp.text


def test_summary_counts_by_event_name(harness, user_factory):
    officer = user_factory(role="officer")
    client = harness.login(officer)
    for _ in range(3):
        client.post("/api/usage/track", json={"event_name": "tab:opened"})
    client.post("/api/usage/track", json={"event_name": "tab:closed"})

    body = client.get("/api/usage/summary", params={"days": 30}).json()
    assert body["days"] == 30
    assert body["counts"]["tab:opened"] == 3
    assert body["counts"]["tab:closed"] == 1
    assert body["total"] == 4


# ── server-side instrumentation hook ─────────────────────────────────────────


def test_calendar_view_writes_usage_event(harness, cursor, chapter_id, user_factory):
    user = user_factory()
    resp = harness.login(user).get("/api/calendar")
    assert resp.status_code == 200, resp.text

    rows = _usage_rows(cursor, chapter_id, "calendar:viewed")
    assert len(rows) == 1
    assert str(rows[0]["member_id"]) == user["id"]


def test_calendar_survives_tracking_failure(harness, user_factory, monkeypatch):
    """Instrumentation is fire-and-forget: a broken tracker never breaks the view."""
    import api.instrumentation.services.usage as usage_svc

    def _boom(*args, **kwargs):
        raise RuntimeError("tracker down")

    monkeypatch.setattr(usage_svc, "track", _boom)
    resp = harness.login(user_factory()).get("/api/calendar")
    assert resp.status_code == 200, resp.text
