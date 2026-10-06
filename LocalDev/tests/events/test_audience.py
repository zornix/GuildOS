"""Audience enforcement — chapter/officer/custom visibility in list and get."""

from __future__ import annotations

import pytest

from api.events.services import events as svc


def _visible_ids(sb, user):
    return {e["id"] for e in svc.list_events(sb, user=user)}


def test_member_cannot_see_officer_event(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer, audience="officers")
    plain = user_factory()

    assert ev["id"] not in _visible_ids(sb_client, plain)
    with pytest.raises(svc.EventNotFound):
        svc.get_event(sb_client, user=plain, event_id=ev["id"])


def test_officer_sees_officer_event(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer, audience="officers")
    assert ev["id"] in _visible_ids(sb_client, officer)


def test_chair_with_officer_view_sees_everything(sb_client, user_factory, create_event, assign_role):
    officer = user_factory(role="officer")
    ev_off = create_event(officer, audience="officers")
    ev_custom = create_event(officer, audience="custom", audience_member_ids=[])

    risk = user_factory()
    assign_role(risk["id"], "risk_chair")  # holds calendar:officer:view
    visible = _visible_ids(sb_client, risk)
    assert ev_off["id"] in visible and ev_custom["id"] in visible


def test_chapter_event_visible_to_everyone(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    ev = create_event(officer, audience="all")
    plain = user_factory()
    assert ev["id"] in _visible_ids(sb_client, plain)


def test_custom_audience_member_sees_event(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    invited = user_factory()
    outsider = user_factory()
    ev = create_event(officer, audience="custom", audience_member_ids=[invited["id"]])

    assert ev["id"] in _visible_ids(sb_client, invited)
    assert svc.get_event(sb_client, user=invited, event_id=ev["id"])["id"] == ev["id"]

    assert ev["id"] not in _visible_ids(sb_client, outsider)
    with pytest.raises(svc.EventNotFound):
        svc.get_event(sb_client, user=outsider, event_id=ev["id"])


def test_supervisor_sees_restricted_event(sb_client, user_factory, create_event, assign_role):
    officer = user_factory(role="officer")
    ev = create_event(officer, audience="officers")
    chair = user_factory()
    assign_role(chair["id"], "social_chair")  # social_chair lacks calendar:officer:view
    svc.add_supervisor(sb_client, actor=officer, event_id=ev["id"], member_id=chair["id"])

    assert ev["id"] in _visible_ids(sb_client, chair)
    assert svc.get_event(sb_client, user=chair, event_id=ev["id"])["id"] == ev["id"]


def test_organizer_sees_custom_event(sb_client, user_factory, create_event):
    officer = user_factory(role="officer")
    helper = user_factory()
    ev = create_event(officer, audience="custom", audience_member_ids=[])
    svc.add_organizer(sb_client, actor=officer, event_id=ev["id"], member_id=helper["id"])

    assert ev["id"] in _visible_ids(sb_client, helper)


def test_update_event_rolls_back_when_audience_is_rejected(sb_client, cursor, user_factory, create_event):
    import uuid
    officer = user_factory(role='officer')
    event = create_event(officer)
    cursor.execute("INSERT INTO chapters(name,organization,school) VALUES (%s,'Test','Test') RETURNING id", (f'foreign-{uuid.uuid4()}',))
    foreign = user_factory(chapter=str(cursor.fetchone()['id']))
    type_name = f'Rejected-{uuid.uuid4()}'
    with pytest.raises(Exception, match='not in chapter'):
        svc.update_event(sb_client, actor=officer, event_id=event['id'], updates={
            'title': 'Rejected edit', 'time': '20:00', 'audience': 'custom',
            'audience_member_ids': [foreign['id']], 'event_type_name': type_name})
    cursor.execute('SELECT title,time,visibility FROM events WHERE id=%s', (event['id'],))
    row = cursor.fetchone()
    assert row['title'] == event['title']
    assert str(row['time']) == str(event['time'])
    assert row['visibility'] == event['visibility']
    cursor.execute('SELECT id FROM event_types WHERE chapter_id=%s AND name=%s', (officer['chapter_id'], type_name))
    assert cursor.fetchall() == []


@pytest.mark.parametrize('wrapper', ['_enqueue', 'notify_event_created'])
@pytest.mark.parametrize('in_tx', [False, True])
def test_notification_wrappers_preserve_transaction_errors(monkeypatch, wrapper, in_tx):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from api.events import notifications
    sb = MagicMock()
    sb._pool = SimpleNamespace(in_tx=in_tx)
    sb.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
    def fail(*args, **kwargs):
        raise RuntimeError('enqueue failed')
    monkeypatch.setattr(notifications, 'enqueue', fail)
    monkeypatch.setattr(notifications, 'enqueue_many', fail)
    def invoke():
        if wrapper == '_enqueue':
            return notifications._enqueue(sb, event_type='EVENT_CREATED')
        return notifications.notify_event_created(sb, chapter_id='chapter', event={'id':'event'})
    if in_tx:
        with pytest.raises(RuntimeError, match='enqueue failed'):
            invoke()
    else:
        assert invoke() in (None, 0)
