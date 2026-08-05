"""Recruitment test harness — reuses the treasury DB fixtures.

Superuser psycopg connection (bypasses RLS); these are RPC/tenant-guard tests
exercising `rc_update_recruit_stage` (migration 0151) directly, in the same
style as tests/attendance/conftest.py.
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
            VALUES (%s, 'Recruitment Test Org', 'Test University')
            RETURNING id
            """,
            (f"rc-test-{uuid.uuid4()}",),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def chapter_member_factory(cursor):
    """Insert an active member into an arbitrary chapter; returns its id."""

    def _make(chapter: str, *, role: str = "officer") -> str:
        cursor.execute(
            """
            INSERT INTO members (chapter_id, name, email, role, status)
            VALUES (%s, %s, %s, %s, 'active')
            RETURNING id
            """,
            (
                chapter,
                f"Member {uuid.uuid4().hex[:8]}",
                f"{uuid.uuid4()}@test.local",
                role,
            ),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def recruit_factory(cursor):
    """Insert a recruit into a chapter; returns its id."""

    def _make(chapter: str, *, stage: str = "lead", phone: str | None = None) -> str:
        cursor.execute(
            """
            INSERT INTO recruits (chapter_id, name, email, phone, stage)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                chapter,
                f"PNM {uuid.uuid4().hex[:8]}",
                f"{uuid.uuid4()}@test.local",
                phone,
                stage,
            ),
        )
        return str(cursor.fetchone()["id"])

    return _make


def update_recruit_stage(cursor, chapter_id, recruit_id, stage, actor_id, key=None):
    cursor.execute(
        "SELECT rc_update_recruit_stage(%s, %s, %s, %s, %s) AS r",
        (chapter_id, recruit_id, stage, actor_id, key),
    )
    return cursor.fetchone()["r"]


def audit_rows(cursor, chapter_id, target_id):
    cursor.execute(
        """
        SELECT action, actor_id, target_table, target_id, metadata
          FROM audit_logs
         WHERE chapter_id = %s AND target_id = %s AND action = 'UPDATE_RECRUIT_STAGE'
         ORDER BY created_at
        """,
        (chapter_id, target_id),
    )
    return cursor.fetchall()
