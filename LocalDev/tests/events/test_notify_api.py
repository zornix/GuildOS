"""Events notify gate - HTTP layer (docs/imp-ev-ph2.md section 5.2 items 3, 4, 6-10).

Items 1, 2, 5 (gate, happy path, D6 re-notify) are covered at the service
level in tests/events/test_notify.py, since they don't turn on HTTP-specific
behavior; this file covers the request/response-shaped assertions (status
codes, response bodies, headers) that need the real app + TestClient.

Runs entirely in MESSAGE_DELIVERY_MODE=dry_run (set by app_on_test_db).
"""

from __future__ import annotations

import psycopg2
import pytest

from api.events.services import events as events_svc


def _preview(client, event_id):
    return client.get(f"/api/events/{event_id}/notify-preview")


def _notify(client, event_id, count, key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        f"/api/events/{event_id}/notify",
        json={"confirmed_recipient_count": count},
        headers=headers,
    )


def _complete_event(create_event, create_job, set_phone, user_factory, sb_client):
    """A notify-gate-complete event (>=1 supervisor, >=1 organizer, >=3 jobs),
    with the creating officer SMS-reachable."""
    officer = user_factory(role="officer")
    ev = create_event(officer)
    organizer = user_factory()
    events_svc.add_organizer(sb_client, actor=organizer, event_id=ev["id"])
    for _ in range(3):
        create_job(event_id=ev["id"])
    set_phone(officer["id"])
    return ev, officer, organizer


# ── Preview (item 10) ────────────────────────────────────────────────────


def test_preview_incomplete_event_no_side_effects(
    cursor, chapter_id, as_member, create_event, set_phone, user_factory
):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    set_phone(officer["id"])
    # 0 organizers, 0 jobs -> incomplete

    resp = _preview(as_member(officer["id"]), ev["id"])
    assert resp.status_code == 200
    body = resp.json()
    by_key = {i["key"]: i for i in body["completeness"]["items"]}
    assert body["completeness"]["is_complete"] is False
    assert by_key["organizers"]["met"] is False
    assert by_key["jobs"]["current"] == 0
    assert body["last_notified_at"] is None

    cursor.execute(
        "SELECT count(*) AS n FROM event_notification_sends WHERE chapter_id = %s",
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 0  # preview has no side effects


# ── No-phone exclusion (item 8) ──────────────────────────────────────────


def test_preview_no_phone_exclusion(as_member, create_event, set_phone, user_factory):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    set_phone(officer["id"])

    reachable = user_factory()
    set_phone(reachable["id"], "+15555550111")

    user_factory()  # phone NULL by default -> no_phone
    user_factory()  # ditto: since 0149 NULL is the only spelling of "no phone",
    # so a whitespace-only phone can no longer be stored (members_phone_e164).

    resp = _preview(as_member(officer["id"]), ev["id"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["recipient_count"] == 2  # officer + reachable
    assert body["no_phone_count"] == 2  # NULL-phone + blank-phone
    assert body["no_consent_count"] == 0  # dry_run reaches everyone with a phone (#89)


# ── Count mismatch (item 3) ──────────────────────────────────────────────


def test_count_mismatch_returns_409_with_fresh_count(
    create_event, create_job, set_phone, user_factory, sb_client, as_member
):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)
    extra = user_factory()
    set_phone(extra["id"], "+15555550112")

    resp = _notify(as_member(officer["id"]), ev["id"], count=99)  # stale
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["recipient_count"] == 2  # officer + extra: the fresh count


# ── Idempotency (item 4) ─────────────────────────────────────────────────


def test_resend_with_same_idempotency_key_does_not_duplicate(
    cursor, chapter_id, create_event, create_job, set_phone, user_factory, sb_client, as_member
):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)
    client = as_member(officer["id"])

    first = _notify(client, ev["id"], count=1, key="notify-blast-1")
    second = _notify(client, ev["id"], count=1, key="notify-blast-1")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]

    cursor.execute(
        "SELECT count(*) AS n FROM event_notification_sends WHERE chapter_id = %s",
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 1
    cursor.execute(
        """
        SELECT count(*) AS n FROM message_outbox
        WHERE chapter_id = %s AND event_type = 'EVENT_NOTIFY'
        """,
        (chapter_id,),
    )
    assert cursor.fetchone()["n"] == 1  # one per recipient, no duplicates


# ── Permissions (D5, item 6) ─────────────────────────────────────────────


def test_notify_organizer_can_send(create_event, create_job, set_phone, user_factory, sb_client, as_member):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)
    resp = _notify(as_member(organizer["id"]), ev["id"], count=1)
    assert resp.status_code == 200, resp.text


def test_notify_supervisor_can_send(create_event, create_job, set_phone, user_factory, sb_client, as_member):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)
    resp = _notify(as_member(officer["id"]), ev["id"], count=1)
    assert resp.status_code == 200, resp.text


def test_notify_plain_member_forbidden(create_event, create_job, set_phone, user_factory, sb_client, as_member):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)
    plain = user_factory()
    resp = _notify(as_member(plain["id"]), ev["id"], count=1)
    assert resp.status_code == 403


def test_notify_member_with_event_update_role_can_send(
    create_event, create_job, set_phone, user_factory, sb_client, as_member, assign_role
):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)
    secretary = user_factory()
    assign_role(secretary["id"], "secretary")  # holds calendar:event:update, not supervisor/organizer
    resp = _notify(as_member(secretary["id"]), ev["id"], count=1)
    assert resp.status_code == 200, resp.text


# ── Cooldown (item 7) ────────────────────────────────────────────────────


def test_immediate_renotify_is_429(create_event, create_job, set_phone, user_factory, sb_client, as_member):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)
    client = as_member(officer["id"])

    first = _notify(client, ev["id"], count=1, key="cooldown-first")
    assert first.status_code == 200, first.text

    second = _notify(client, ev["id"], count=1, key="cooldown-second")
    assert second.status_code == 429


# ── Append-only guarantees (item 9) ──────────────────────────────────────


def test_notification_sends_are_append_only(
    cursor, create_event, create_job, set_phone, user_factory, sb_client, as_member
):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)
    resp = _notify(as_member(officer["id"]), ev["id"], count=1)
    assert resp.status_code == 200, resp.text
    send_id = resp.json()["id"]

    with pytest.raises(psycopg2.DatabaseError, match="append-only"):
        cursor.execute(
            "UPDATE event_notification_sends SET body_snapshot = 'tampered' WHERE id = %s",
            (send_id,),
        )
    with pytest.raises(psycopg2.DatabaseError, match="forbidden"):
        cursor.execute("DELETE FROM event_notification_sends WHERE id = %s", (send_id,))
