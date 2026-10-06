"""Organizers — volunteer/leave, assign permission, soft-minimum flagging, audit."""

from __future__ import annotations

import pytest

from api.events.services import events as svc


def test_organizers_needed_progression(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)

    # D3 (docs/events-dev-status.md §2): ORGANIZER_SOFT_MIN dropped 2 -> 1.
    got = svc.get_event(sb_client, user=officer, event_id=ev["id"])
    assert got["organizer_count"] == 0 and got["organizers_needed"] == 1

    a = user_factory()
    svc.add_organizer(sb_client, actor=a, event_id=ev["id"])
    got = svc.get_event(sb_client, user=officer, event_id=ev["id"])
    assert got["organizer_count"] == 1 and got["organizers_needed"] == 0

    b = user_factory()
    svc.add_organizer(sb_client, actor=b, event_id=ev["id"])
    got = svc.get_event(sb_client, user=officer, event_id=ev["id"])
    assert got["organizer_count"] == 2 and got["organizers_needed"] == 0


def test_volunteer_is_idempotent(sb_client, cursor, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    a = user_factory()

    first = svc.add_organizer(sb_client, actor=a, event_id=ev["id"])
    second = svc.add_organizer(sb_client, actor=a, event_id=ev["id"])
    assert first["id"] == second["id"]

    cursor.execute("SELECT count(*) AS n FROM event_organizers WHERE event_id = %s", (ev["id"],))
    assert cursor.fetchone()["n"] == 1


def test_volunteer_source_vs_assigned_source(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    a = user_factory()
    b = user_factory()

    row = svc.add_organizer(sb_client, actor=a, event_id=ev["id"])
    assert row["source"] == "volunteer"

    row = svc.add_organizer(sb_client, actor=officer, event_id=ev["id"], member_id=b["id"])
    assert row["source"] == "assigned"


def test_member_cannot_assign_other_member(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    a = user_factory()
    b = user_factory()

    with pytest.raises(svc.NotPermitted):
        svc.add_organizer(sb_client, actor=a, event_id=ev["id"], member_id=b["id"])


def test_self_leave_and_officer_remove(sb_client, cursor, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    a = user_factory()
    b = user_factory()
    svc.add_organizer(sb_client, actor=a, event_id=ev["id"])
    svc.add_organizer(sb_client, actor=b, event_id=ev["id"])

    # self-leave
    svc.remove_organizer(sb_client, actor=a, event_id=ev["id"], member_id=a["id"])
    # officer removes other
    svc.remove_organizer(sb_client, actor=officer, event_id=ev["id"], member_id=b["id"])

    cursor.execute("SELECT count(*) AS n FROM event_organizers WHERE event_id = %s", (ev["id"],))
    assert cursor.fetchone()["n"] == 0


def test_member_cannot_remove_other(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    a = user_factory()
    b = user_factory()
    svc.add_organizer(sb_client, actor=b, event_id=ev["id"])

    with pytest.raises(svc.NotPermitted):
        svc.remove_organizer(sb_client, actor=a, event_id=ev["id"], member_id=b["id"])


def test_add_organizer_writes_audit_log(sb_client, cursor, chapter_id, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    a = user_factory()
    svc.add_organizer(sb_client, actor=a, event_id=ev["id"])

    cursor.execute(
        """
        SELECT 1 FROM audit_logs
        WHERE chapter_id = %s AND action = 'ADD_EVENT_ORGANIZER' AND target_id = %s
        """,
        (chapter_id, ev["id"]),
    )
    assert cursor.fetchone() is not None


@pytest.mark.parametrize('role', ['organizer', 'supervisor'])
def test_reassigned_role_is_notified_again(sb_client, cursor, user_factory, create_event, assign_role, role):
    actor = user_factory(role='officer')
    target = user_factory()
    assign_role(target['id'], 'social_chair')
    event = create_event(actor)
    add = getattr(svc, f'add_{role}')
    remove = getattr(svc, f'remove_{role}')
    add(sb_client, actor=actor, event_id=event['id'], member_id=target['id'])
    remove(sb_client, actor=actor, event_id=event['id'], member_id=target['id'])
    add(sb_client, actor=actor, event_id=event['id'], member_id=target['id'])
    cursor.execute("SELECT count(*) AS n FROM message_outbox WHERE chapter_id=%s AND target_id=%s AND member_id=%s AND event_type='EVENT_ROLE_ASSIGNED'", (actor['chapter_id'],event['id'],target['id']))
    assert cursor.fetchone()['n'] == 2


@pytest.mark.parametrize('role', ['organizer', 'supervisor'])
def test_retry_of_one_assignment_notifies_once(sb_client, cursor, user_factory, create_event, assign_role, role):
    actor = user_factory(role='officer')
    target = user_factory()
    assign_role(target['id'], 'social_chair')
    event = create_event(actor)
    add = getattr(svc, f'add_{role}')
    for _ in range(2):
        add(sb_client, actor=actor, event_id=event['id'], member_id=target['id'], idempotency_key='one-assignment')
    cursor.execute("SELECT count(*) AS n FROM message_outbox WHERE chapter_id=%s AND target_id=%s AND member_id=%s AND event_type='EVENT_ROLE_ASSIGNED'", (actor['chapter_id'],event['id'],target['id']))
    assert cursor.fetchone()['n'] == 1
