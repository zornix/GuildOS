"""Reuse the treasury DB harness fixtures (db_url, db_conn, cursor, chapter_id, …)."""

from __future__ import annotations

import uuid

import pytest

from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.fixture
def task_factory(cursor, chapter_id):
    """Insert a task directly (reads bypass the RPC; commit RPCs are under test)."""

    def _make(
        *,
        title: str | None = None,
        event_id: str | None = None,
        status: str = "open",
        assigned_member_id: str | None = None,
        chapter: str | None = None,
    ) -> str:
        cursor.execute(
            """
            INSERT INTO tasks (chapter_id, title, status, event_id, assigned_member_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                chapter or chapter_id,
                title or f"Task {uuid.uuid4().hex[:8]}",
                status,
                event_id,
                assigned_member_id,
            ),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def event_factory(cursor, chapter_id):
    """Insert an event whose start is `hours_from_now` away (server clock, so the
    RPC's now()-based math lines up regardless of the server timezone)."""

    def _make(*, hours_from_now: float) -> str:
        cursor.execute(
            """
            INSERT INTO events (chapter_id, title, date, time, location)
            VALUES (
                %s, %s,
                (now() + %s * interval '1 hour')::date,
                (now() + %s * interval '1 hour')::time,
                'Test Hall'
            )
            RETURNING id
            """,
            (chapter_id, f"Event {uuid.uuid4().hex[:8]}", hours_from_now, hours_from_now),
        )
        return str(cursor.fetchone()["id"])

    return _make


def commit_task(cursor, chapter_id, task_id, member_id, actor_id=None, key=None):
    cursor.execute(
        "SELECT tk_commit_task(%s, %s, %s, %s, %s) AS r",
        (chapter_id, task_id, member_id, actor_id or member_id, key),
    )
    return cursor.fetchone()["r"]


def uncommit_task(cursor, chapter_id, task_id, member_id, actor_id=None, reason=None, key=None):
    cursor.execute(
        "SELECT tk_uncommit_task(%s, %s, %s, %s, %s, %s) AS r",
        (chapter_id, task_id, member_id, actor_id or member_id, reason, key),
    )
    return cursor.fetchone()["r"]
