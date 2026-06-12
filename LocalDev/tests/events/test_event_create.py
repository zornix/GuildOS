"""Event creation through ev_create_event — flags, audit, idempotency, audience."""

from __future__ import annotations

import json


def _meta(row):
    meta = row["metadata"]
    return json.loads(meta) if isinstance(meta, str) else meta


def test_finable_defaults_false(user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    assert ev["finable"] is False
    assert ev["required"] is False


def test_finable_flag_persisted(cursor, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer, finable=True, required=True)
    assert ev["finable"] is True

    cursor.execute("SELECT finable, required FROM events WHERE id = %s", (ev["id"],))
    row = cursor.fetchone()
    assert row["finable"] is True and row["required"] is True


def test_create_writes_audit_log(cursor, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer, title="Audited Event")

    cursor.execute(
        """
        SELECT * FROM audit_logs
        WHERE chapter_id = %s AND action = 'CREATE_EVENT' AND target_id = %s
        """,
        (chapter_id, ev["id"]),
    )
    row = cursor.fetchone()
    assert row is not None
    assert row["actor_id"] == officer["id"]
    assert row["target_table"] == "events"
    assert _meta(row)["title"] == "Audited Event"


def test_create_is_idempotent(user_factory, create_event):
    officer = user_factory(role="officer")
    first = create_event(officer, idempotency_key="ev-idem-1")
    second = create_event(officer, idempotency_key="ev-idem-1")
    assert first["id"] == second["id"]


def test_create_custom_audience_persists_rows(cursor, user_factory, create_event):
    officer = user_factory(role="officer")
    a = user_factory()
    b = user_factory()
    ev = create_event(officer, audience="custom", audience_member_ids=[a["id"], b["id"]])
    assert ev["visibility"] == "custom"

    cursor.execute(
        "SELECT member_id FROM event_audience_members WHERE event_id = %s", (ev["id"],)
    )
    assert {str(r["member_id"]) for r in cursor.fetchall()} == {a["id"], b["id"]}


def test_audience_shorthand_maps_to_visibility(user_factory, create_event):
    officer = user_factory(role="officer")
    assert create_event(officer, audience="all")["visibility"] == "chapter"
    assert create_event(officer, audience="officers")["visibility"] == "officer"
