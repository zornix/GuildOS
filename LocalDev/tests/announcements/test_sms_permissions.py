"""SMS permission gate — `announcements:send:sms` is President/Secretary only.

Treasurer and the generic legacy officer hold `announcements:send` (in-app) but
must NOT be able to preview or fire the SMS blast.
"""

from __future__ import annotations


def _preview(client, ann_id):
    return client.get(f"/api/announcements/{ann_id}/sms-preview")


def _send(client, ann_id, count=0):
    return client.post(
        f"/api/announcements/{ann_id}/send-sms",
        json={"confirmed_recipient_count": count},
    )


def test_president_can_preview_and_send(president, as_member, announcement_factory):
    ann = announcement_factory()
    client = as_member(president)

    preview = _preview(client, ann)
    assert preview.status_code == 200
    count = preview.json()["recipient_count"]

    sent = _send(client, ann, count)
    assert sent.status_code == 200, sent.text


def test_secretary_can_preview_and_send(secretary, as_member, announcement_factory):
    ann = announcement_factory()
    client = as_member(secretary)

    preview = _preview(client, ann)
    assert preview.status_code == 200

    sent = _send(client, ann, preview.json()["recipient_count"])
    assert sent.status_code == 200, sent.text


def test_treasurer_gets_403(member_factory, give_role, as_member, announcement_factory):
    treasurer = member_factory()
    give_role(treasurer, "treasurer")
    ann = announcement_factory()
    client = as_member(treasurer)

    assert _preview(client, ann).status_code == 403
    assert _send(client, ann).status_code == 403


def test_generic_officer_gets_403(member_factory, as_member, announcement_factory):
    officer = member_factory(role="officer")  # legacy officer: has announcements:send
    ann = announcement_factory()
    client = as_member(officer)

    assert _preview(client, ann).status_code == 403
    assert _send(client, ann).status_code == 403


def test_plain_member_gets_403(member_factory, as_member, announcement_factory):
    member = member_factory()
    ann = announcement_factory()
    client = as_member(member)

    assert _preview(client, ann).status_code == 403
    assert _send(client, ann).status_code == 403
    assert client.get("/api/announcements/sms-log").status_code == 403
