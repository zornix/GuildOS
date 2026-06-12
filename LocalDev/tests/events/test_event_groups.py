"""Event groups — linking related events and sibling listing."""

from __future__ import annotations

from api.events.services import events as svc


def test_group_with_event_creates_and_shares_group(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    setup = create_event(officer, title="Setup")
    assert setup["event_group_id"] is None

    main = create_event(officer, title="Main", group_with_event_id=setup["id"])
    assert main["event_group_id"] is not None

    refreshed = svc.get_event(sb_client, user=officer, event_id=setup["id"])
    assert refreshed["event_group_id"] == main["event_group_id"]


def test_group_reused_for_third_event(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    setup = create_event(officer, title="Setup")
    main = create_event(officer, title="Main", group_with_event_id=setup["id"])
    cleanup = create_event(officer, title="Cleanup", group_with_event_id=setup["id"])
    assert cleanup["event_group_id"] == main["event_group_id"]


def test_get_event_lists_siblings(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    setup = create_event(officer, title="Setup", date="2026-07-01")
    main = create_event(officer, title="Main", date="2026-07-02", group_with_event_id=setup["id"])
    cleanup = create_event(officer, title="Cleanup", date="2026-07-03", group_with_event_id=main["id"])

    got = svc.get_event(sb_client, user=officer, event_id=main["id"])
    assert got["group_id"] == main["event_group_id"]
    siblings = {e["id"]: e for e in got["group_events"]}
    assert set(siblings) == {setup["id"], cleanup["id"]}
    assert siblings[setup["id"]]["title"] == "Setup"
    assert "date" in siblings[setup["id"]]


def test_ungrouped_event_has_no_siblings(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    got = svc.get_event(sb_client, user=officer, event_id=ev["id"])
    assert got["group_id"] is None
    assert got["group_events"] == []


def test_explicit_event_group_id_accepted(cursor, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    cursor.execute(
        "INSERT INTO event_groups (chapter_id, name) VALUES (%s, 'Formal Weekend') RETURNING id",
        (chapter_id,),
    )
    group_id = str(cursor.fetchone()["id"])
    ev = create_event(officer, event_group_id=group_id)
    assert ev["event_group_id"] == group_id
