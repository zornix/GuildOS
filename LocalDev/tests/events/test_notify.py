"""Notify gate — service-level tests (spec §2.7, docs/imp-ev-ph2.md §5.2 items 1, 2, 5).

Calls `api.events.services.notifications` directly (no HTTP layer). Runs in
MESSAGE_DELIVERY_MODE=dry_run (the default): nothing leaves the process.

HTTP-layer tests for the notify-preview/notify routes (§5.2 items 3, 4, 6-10)
live in tests/events/test_notify_api.py.
"""

from __future__ import annotations

import pytest

from api.events.services import events as events_svc
from api.events.services import notifications as svc


def _complete_event(create_event, create_job, set_phone, user_factory, sb_client, *, jobs=3):
    """An event satisfying the D7 gate: creator is auto-supervisor (0141), +1
    organizer, +N non-cancelled jobs. One member (the officer) has a phone."""
    officer = user_factory(role="officer")
    ev = create_event(officer)
    organizer = user_factory()
    events_svc.add_organizer(sb_client, actor=organizer, event_id=ev["id"])
    for _ in range(jobs):
        create_job(event_id=ev["id"])
    set_phone(officer["id"])
    return ev, officer, organizer


# ── Gate (item 1) ─────────────────────────────────────────────────────────


def test_notify_blocked_when_no_organizers(sb_client, create_event, create_job, set_phone, user_factory):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    for _ in range(3):
        create_job(event_id=ev["id"])
    set_phone(officer["id"])

    with pytest.raises(svc.EventIncomplete) as exc_info:
        svc.notify_event(sb_client, actor=officer, event_id=ev["id"], confirmed_recipient_count=1)
    by_key = {i["key"]: i for i in exc_info.value.completeness["items"]}
    assert by_key["organizers"]["met"] is False
    assert exc_info.value.completeness["is_complete"] is False


def test_notify_blocked_with_only_two_jobs(sb_client, create_event, create_job, set_phone, user_factory):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    organizer = user_factory()
    events_svc.add_organizer(sb_client, actor=organizer, event_id=ev["id"])
    for _ in range(2):
        create_job(event_id=ev["id"])
    set_phone(officer["id"])

    with pytest.raises(svc.EventIncomplete) as exc_info:
        svc.notify_event(sb_client, actor=officer, event_id=ev["id"], confirmed_recipient_count=1)
    by_key = {i["key"]: i for i in exc_info.value.completeness["items"]}
    assert by_key["jobs"]["met"] is False
    assert by_key["jobs"]["current"] == 2


def test_cancelled_jobs_dont_count_toward_the_gate(sb_client, create_event, create_job, set_phone, user_factory):
    officer = user_factory(role="officer")
    ev = create_event(officer)
    organizer = user_factory()
    events_svc.add_organizer(sb_client, actor=organizer, event_id=ev["id"])
    create_job(event_id=ev["id"])
    create_job(event_id=ev["id"])
    create_job(event_id=ev["id"], status="cancelled")  # doesn't count -> only 2 real jobs
    set_phone(officer["id"])

    with pytest.raises(svc.EventIncomplete) as exc_info:
        svc.notify_event(sb_client, actor=officer, event_id=ev["id"], confirmed_recipient_count=1)
    by_key = {i["key"]: i for i in exc_info.value.completeness["items"]}
    assert by_key["jobs"]["current"] == 2
    assert by_key["jobs"]["met"] is False


# ── Happy path, dry_run (item 2) ────────────────────────────────────────────


def test_notify_happy_path_dry_run(
    sb_client, cursor, chapter_id, create_event, create_job, set_phone, user_factory
):
    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)

    send = svc.notify_event(
        sb_client, actor=officer, event_id=ev["id"], confirmed_recipient_count=1
    )
    assert send["status"] == "sent"  # dry_run dispatch marked it sent
    assert send["recipient_count"] == 1
    assert str(send["sender_id"]) == officer["id"]
    assert ev["title"] in send["body_snapshot"]
    assert "3 open jobs" in send["body_snapshot"]

    cursor.execute(
        "SELECT * FROM event_notification_sends WHERE chapter_id = %s", (chapter_id,)
    )
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "sent"

    cursor.execute(
        """
        SELECT * FROM message_outbox
        WHERE chapter_id = %s AND event_type = 'EVENT_NOTIFY'
        """,
        (chapter_id,),
    )
    outbox = cursor.fetchall()
    assert len(outbox) == 1
    assert str(outbox[0]["member_id"]) == officer["id"]
    assert outbox[0]["status"] == "sent"
    assert outbox[0]["delivery_mode"] == "sms"

    cursor.execute(
        """
        SELECT * FROM audit_logs
        WHERE chapter_id = %s AND action = 'EVENT_NOTIFY'
        """,
        (chapter_id,),
    )
    audits = cursor.fetchall()
    assert len(audits) == 1
    assert str(audits[0]["target_id"]) == send["id"]

    updated = events_svc.get_event(sb_client, user=officer, event_id=ev["id"])
    assert updated["last_notified_at"] is not None


# ── Re-notify after cooldown elapses (D6, item 5) ───────────────────────────


def test_renotify_after_cooldown_creates_fresh_send_with_distinct_dedup_keys(
    sb_client, cursor, chapter_id, create_event, create_job, set_phone, user_factory
):
    import json

    ev, officer, organizer = _complete_event(create_event, create_job, set_phone, user_factory, sb_client)

    # Seed a stale prior send (>1h old) directly -- the append-only trigger
    # blocks UPDATEing created_at on a real send row, so we insert history
    # rather than backdating one.
    cursor.execute(
        """
        INSERT INTO event_notification_sends
            (chapter_id, event_id, sender_id, recipient_count,
             recipient_member_ids, body_snapshot, delivery_mode, status, created_at)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, 'sent', now() - interval '2 hours')
        RETURNING id
        """,
        (chapter_id, ev["id"], officer["id"], 1, json.dumps([officer["id"]]), "old body", "dry_run"),
    )
    old_send_id = str(cursor.fetchone()["id"])

    send = svc.notify_event(
        sb_client, actor=officer, event_id=ev["id"], confirmed_recipient_count=1
    )
    assert send["id"] != old_send_id

    cursor.execute(
        """
        SELECT dedup_key FROM message_outbox
        WHERE chapter_id = %s AND event_type = 'EVENT_NOTIFY'
        """,
        (chapter_id,),
    )
    keys = [r["dedup_key"] for r in cursor.fetchall()]
    assert len(keys) == 1  # only the fresh send fanned out (old one was seeded directly)
    assert send["id"] in keys[0]

    updated = events_svc.get_event(sb_client, user=officer, event_id=ev["id"])
    assert updated["last_notified_at"] is not None
