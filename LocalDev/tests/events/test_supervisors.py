"""Events V1 Phase 1 — co-supervisors, backfill, and end-time validation.

Superuser connection bypasses RLS (existing treasury-test pattern); mutations go
through the events service layer so authorization is exercised too.
"""

from __future__ import annotations

import uuid

import pytest

from api.events.services import events as svc


def _supervisor_ids(sb, event_id: str) -> set[str]:
    rows = (
        sb.table("event_supervisors").select("member_id").eq("event_id", event_id).execute()
    ).data or []
    return {str(r["member_id"]) for r in rows}


# ── creator is always a supervisor ────────────────────────────────────────────


def test_creator_is_auto_supervisor(sb_client, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)

    supervisors = {s["member_id"]: s for s in ev["supervisors"]}
    assert officer["id"] in supervisors
    assert supervisors[officer["id"]]["is_creator"] is True
    assert _supervisor_ids(sb_client, ev["id"]) == {officer["id"]}


# ── add a co-supervisor ───────────────────────────────────────────────────────


def test_add_officer_cosupervisor_and_idempotent(
    sb_client, chapter_id, user_factory, create_event, assign_role
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    chair = user_factory()
    assign_role(chair["id"], "social_chair")

    result = svc.add_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=chair["id"])
    ids = {s["member_id"] for s in result["supervisors"]}
    assert ids == {officer["id"], chair["id"]}

    # Idempotent re-add is a no-op (still exactly two supervisors).
    again = svc.add_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=chair["id"])
    assert {s["member_id"] for s in again["supervisors"]} == {officer["id"], chair["id"]}
    assert _supervisor_ids(sb_client, ev["id"]) == {officer["id"], chair["id"]}


def test_add_non_officer_rejected(
    sb_client, chapter_id, user_factory, create_event
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    plain = user_factory()  # no officer/chair role

    with pytest.raises(svc.NotEligible):
        svc.add_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=plain["id"])


# ── remove: creator locked, min-1 invariant ───────────────────────────────────


def test_remove_cosupervisor_and_invariants(
    sb_client, chapter_id, user_factory, create_event, assign_role
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    chair = user_factory()
    assign_role(chair["id"], "brotherhood_chair")
    svc.add_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=chair["id"])

    # Removing the co-supervisor is fine.
    result = svc.remove_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=chair["id"])
    assert {s["member_id"] for s in result["supervisors"]} == {officer["id"]}

    # Removing the creator is blocked (and this is also the last supervisor).
    with pytest.raises(svc.SupervisorRuleViolation):
        svc.remove_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=officer["id"])
    assert _supervisor_ids(sb_client, ev["id"]) == {officer["id"]}


# ── authorization ─────────────────────────────────────────────────────────────


def test_non_supervisor_without_permission_cannot_manage(
    sb_client, chapter_id, user_factory, create_event, assign_role
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    chair = user_factory()
    assign_role(chair["id"], "social_chair")
    svc.add_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=chair["id"])

    outsider = user_factory(role="member")  # not a supervisor, no calendar:event:update

    with pytest.raises(svc.NotPermitted):
        svc.add_supervisor(sb_client, actor=outsider, event_id=ev["id"], member_id=chair["id"])
    with pytest.raises(svc.NotPermitted):
        svc.remove_supervisor(sb_client, actor=outsider, event_id=ev["id"], member_id=chair["id"])


# ── backfill (0141) ───────────────────────────────────────────────────────────


def test_backfill_legacy_supervisor_row(sb_client, cursor, chapter_id, member_factory):
    """A legacy event (creator + single supervisor_member_id) backfills to two
    supervisor rows, creator winning is_creator."""
    creator = member_factory()
    legacy_sup = member_factory()
    cursor.execute(
        """
        INSERT INTO events (chapter_id, title, date, time, location, created_by, supervisor_member_id)
        VALUES (%s, %s, CURRENT_DATE, TIME '19:00', 'Hall', %s, %s)
        RETURNING id
        """,
        (chapter_id, f"Legacy {uuid.uuid4().hex[:6]}", creator, legacy_sup),
    )
    event_id = str(cursor.fetchone()["id"])

    # Re-run the idempotent backfill statements from 0141.
    cursor.execute(
        """
        INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator)
        SELECT e.chapter_id, e.id, e.created_by, TRUE
          FROM events e WHERE e.id = %s AND e.created_by IS NOT NULL
        ON CONFLICT (event_id, member_id) DO NOTHING
        """,
        (event_id,),
    )
    cursor.execute(
        """
        INSERT INTO event_supervisors (chapter_id, event_id, member_id, is_creator)
        SELECT e.chapter_id, e.id, e.supervisor_member_id, FALSE
          FROM events e WHERE e.id = %s AND e.supervisor_member_id IS NOT NULL
        ON CONFLICT (event_id, member_id) DO NOTHING
        """,
        (event_id,),
    )

    cursor.execute(
        "SELECT member_id, is_creator FROM event_supervisors WHERE event_id = %s", (event_id,)
    )
    rows = {str(r["member_id"]): r["is_creator"] for r in cursor.fetchall()}
    assert rows == {creator: True, legacy_sup: False}


# ── end-time validation ───────────────────────────────────────────────────────


def test_end_before_start_rejected(sb_client, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    with pytest.raises(svc.InvalidTimeRange):
        create_event(officer, date="2026-09-01", time="19:00", end_time="18:00")


def test_valid_end_range_persists(sb_client, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(
        officer, date="2026-09-01", time="19:00", end_time="21:30", invite_link="https://x.test/e"
    )
    assert ev["end_time"].startswith("21:30")
    assert ev["invite_link"] == "https://x.test/e"
