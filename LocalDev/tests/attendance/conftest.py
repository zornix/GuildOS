"""Attendance tenant-guard harness — reuses the treasury DB fixtures.

Superuser psycopg connection (bypasses RLS); these are trigger/RPC/atomicity
tests, per imp-tenant-guards.md Verification.
"""

from __future__ import annotations

import uuid

import pytest

from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.fixture
def chapter_factory(cursor):
    """Insert a fresh chapter; returns its id. For cross-chapter isolation tests."""

    def _make() -> str:
        cursor.execute(
            """
            INSERT INTO chapters (name, organization, school)
            VALUES (%s, 'Attendance Test Org', 'Test University')
            RETURNING id
            """,
            (f"at-test-{uuid.uuid4()}",),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def event_factory(cursor):
    """Insert an event into a given chapter; returns its id."""

    def _make(chapter: str, *, required: bool = False) -> str:
        cursor.execute(
            """
            INSERT INTO events (chapter_id, title, date, time, location, required)
            VALUES (%s, %s, now()::date, now()::time, 'Test Hall', %s)
            RETURNING id
            """,
            (chapter, f"Event {uuid.uuid4().hex[:8]}", required),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def excuse_factory(cursor):
    """Insert a pending excuse for (event, member) in a chapter; returns its id."""

    def _make(chapter: str, event_id: str, member_id: str, *, reason: str = "sick") -> str:
        cursor.execute(
            """
            INSERT INTO excuses (chapter_id, event_id, member_id, reason, status)
            VALUES (%s, %s, %s, %s, 'pending')
            RETURNING id
            """,
            (chapter, event_id, member_id, reason),
        )
        return str(cursor.fetchone()["id"])

    return _make


def set_attendance(cursor, chapter_id, event_id, member_id, status, actor_id,
                   reason=None, key=None):
    cursor.execute(
        "SELECT at_set_attendance(%s, %s, %s, %s, %s, %s, %s) AS r",
        (chapter_id, event_id, member_id, status, reason, actor_id, key),
    )
    return cursor.fetchone()["r"]


def review_excuse(cursor, chapter_id, excuse_id, status, actor_id, key=None):
    cursor.execute(
        "SELECT at_review_excuse(%s, %s, %s, %s, %s) AS r",
        (chapter_id, excuse_id, status, actor_id, key),
    )
    return cursor.fetchone()["r"]
