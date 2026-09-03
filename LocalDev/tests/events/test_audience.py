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
