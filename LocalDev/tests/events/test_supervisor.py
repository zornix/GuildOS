"""Supervisor — chair eligibility, volunteer vs assign, replacement + audit."""

from __future__ import annotations

import pytest

from api.events.services import events as svc


def test_non_chair_rejected(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    plain = user_factory()

    with pytest.raises(svc.NotEligible):
        svc.set_supervisor(sb_client, actor=plain, event_id=ev["id"], member_id=plain["id"])


def test_chair_can_volunteer_self(sb_client, cursor, user_factory, create_event, assign_role):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    chair = user_factory()
    assign_role(chair["id"], "social_chair")

    result = svc.set_supervisor(sb_client, actor=chair, event_id=ev["id"], member_id=chair["id"])
    assert result["supervisor_member_id"] == chair["id"]

    cursor.execute("SELECT supervisor_member_id FROM events WHERE id = %s", (ev["id"],))
    assert str(cursor.fetchone()["supervisor_member_id"]) == chair["id"]


def test_member_cannot_assign_someone_else(sb_client, user_factory, create_event, assign_role):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    plain = user_factory()
    chair = user_factory()
    assign_role(chair["id"], "risk_chair")

    with pytest.raises(svc.NotPermitted):
        svc.set_supervisor(sb_client, actor=plain, event_id=ev["id"], member_id=chair["id"])


def test_officer_can_assign_any_chair(sb_client, user_factory, create_event, assign_role):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    chair = user_factory()
    assign_role(chair["id"], "philanthropy_chair")

    result = svc.set_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=chair["id"])
    assert result["supervisor_member_id"] == chair["id"]


def test_officer_assigning_non_chair_rejected(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    plain = user_factory()

    with pytest.raises(svc.NotEligible):
        svc.set_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=plain["id"])


def test_replacement_allowed_and_audited(sb_client, cursor, chapter_id, user_factory, create_event, assign_role):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    first = user_factory()
    second = user_factory()
    assign_role(first["id"], "brotherhood_chair")
    assign_role(second["id"], "standards_chair")

    svc.set_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=first["id"])
    result = svc.set_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=second["id"])
    assert result["supervisor_member_id"] == second["id"]

    cursor.execute(
        """
        SELECT count(*) AS n FROM audit_logs
        WHERE chapter_id = %s AND action = 'SET_EVENT_SUPERVISOR' AND target_id = %s
        """,
        (chapter_id, ev["id"]),
    )
    assert cursor.fetchone()["n"] == 2
