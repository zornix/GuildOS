"""Automatic event email (ADR-0005): creation fan-out and role assignment.

The manual "Notify members" SMS blast is covered elsewhere and is unaffected.
"""

from __future__ import annotations

import pytest

from api.events.notifications import notify_event_created, notify_role_assigned


@pytest.fixture
def outbox_for(cursor, chapter_id):
    def _read(event_type: str, event_id: str) -> list[dict]:
        cursor.execute(
            """
            SELECT member_id, channel, payload FROM message_outbox
             WHERE chapter_id = %s AND event_type = %s AND target_id = %s
            """,
            (chapter_id, event_type, event_id),
        )
        return [dict(r) for r in cursor.fetchall()]

    return _read


@pytest.fixture
def event_row(cursor, chapter_id):
    cursor.execute(
        """
        INSERT INTO events (chapter_id, title, date, time, location)
        VALUES (%s, 'Rush Kickoff', '2026-10-01', '18:00', 'The House')
        RETURNING id, title, date, time, location
        """,
        (chapter_id,),
    )
    return dict(cursor.fetchone())


def test_event_created_reaches_every_active_member(
    sb_client, cursor, chapter_id, member_factory, event_row, outbox_for
):
    active = [member_factory() for _ in range(3)]
    inactive = member_factory()
    cursor.execute("UPDATE members SET status = 'invited' WHERE id = %s", (inactive,))

    queued = notify_event_created(sb_client, chapter_id=chapter_id, event=event_row)

    rows = outbox_for("EVENT_CREATED", str(event_row["id"]))
    assert queued == len(rows) == len(active)
    assert {str(r["member_id"]) for r in rows} == set(active)
    assert {r["channel"] for r in rows} == {"email"}
    assert rows[0]["payload"]["title"] == "Rush Kickoff"
    assert rows[0]["payload"]["location"] == "The House"


def test_event_created_is_enqueued_once_per_member(
    sb_client, chapter_id, member_factory, event_row, outbox_for
):
    member_factory()
    notify_event_created(sb_client, chapter_id=chapter_id, event=event_row)
    assert notify_event_created(sb_client, chapter_id=chapter_id, event=event_row) == 0
    assert len(outbox_for("EVENT_CREATED", str(event_row["id"]))) == 1


def test_role_assignment_emails_the_assigned_member(
    sb_client, chapter_id, member_factory, event_row, outbox_for
):
    member = member_factory()
    notify_role_assigned(
        sb_client,
        chapter_id=chapter_id,
        event=event_row,
        member_id=member,
        role="supervisor",
    )

    rows = outbox_for("EVENT_ROLE_ASSIGNED", str(event_row["id"]))
    assert len(rows) == 1
    assert str(rows[0]["member_id"]) == member
    assert rows[0]["channel"] == "email"
    assert rows[0]["payload"]["role"] == "supervisor"


def test_the_two_roles_are_separate_messages(
    sb_client, chapter_id, member_factory, event_row, outbox_for
):
    """Someone who organizes and supervises the same event hears about both."""
    member = member_factory()
    for role in ("organizer", "supervisor"):
        notify_role_assigned(
            sb_client,
            chapter_id=chapter_id,
            event=event_row,
            member_id=member,
            role=role,
        )

    rows = outbox_for("EVENT_ROLE_ASSIGNED", str(event_row["id"]))
    assert sorted(r["payload"]["role"] for r in rows) == ["organizer", "supervisor"]
