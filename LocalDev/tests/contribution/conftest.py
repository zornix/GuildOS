"""Contribution test harness — treasury DB fixtures plus the HTTP harness.

Every test works inside its own `chapter_id` (fresh chapter per test), so runs
in parallel with other agents never collide. `cleanup_chapter` removes the rows
this domain creates afterwards; child rows (organizers, supervisors, chairs,
commitments, attendance) go with their parents by ON DELETE CASCADE.
"""

from __future__ import annotations

import uuid

import pytest

from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.fixture
def assign_role(cursor, chapter_id):
    """Insert a member_roles row directly (test shortcut; prod uses rbac_assign_role)."""

    def _assign(member_id: str, role_key: str, *, chapter: str | None = None) -> None:
        cursor.execute(
            """
            INSERT INTO member_roles (chapter_id, member_id, role_key)
            VALUES (%s, %s, %s)
            ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING
            """,
            (chapter or chapter_id, member_id, role_key),
        )

    return _assign


@pytest.fixture(autouse=True)
def cleanup_chapter(cursor, chapter_id):
    """Drop this test's events / initiatives / tasks after the test."""
    yield
    for table in ("attendance",):
        cursor.execute(
            f"DELETE FROM {table} WHERE event_id IN "
            "(SELECT id FROM events WHERE chapter_id = %s)",
            (chapter_id,),
        )
    for table in ("tasks", "initiatives", "events"):
        cursor.execute(f"DELETE FROM {table} WHERE chapter_id = %s", (chapter_id,))


@pytest.fixture
def create_event(cursor, chapter_id):
    """Insert an event row directly; returns its id."""

    def _make(*, title: str | None = None, date: str = "2026-03-01", chapter: str | None = None) -> str:
        cursor.execute(
            """
            INSERT INTO events (chapter_id, title, date, time, location, required)
            VALUES (%s, %s, %s, '19:00', 'Chapter House', TRUE)
            RETURNING id
            """,
            (chapter or chapter_id, title or f"Event {uuid.uuid4().hex[:8]}", date),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def add_organizer(cursor, chapter_id):
    def _add(event_id: str, member_id: str, *, chapter: str | None = None) -> None:
        cursor.execute(
            "INSERT INTO event_organizers (chapter_id, event_id, member_id) VALUES (%s, %s, %s)",
            (chapter or chapter_id, event_id, member_id),
        )

    return _add


@pytest.fixture
def add_supervisor(cursor, chapter_id):
    def _add(event_id: str, member_id: str, *, chapter: str | None = None) -> None:
        cursor.execute(
            "INSERT INTO event_supervisors (chapter_id, event_id, member_id) VALUES (%s, %s, %s)",
            (chapter or chapter_id, event_id, member_id),
        )

    return _add


@pytest.fixture
def check_in(cursor):
    def _check(event_id: str, member_id: str) -> None:
        cursor.execute(
            """
            INSERT INTO attendance (event_id, member_id, checked_in, checked_in_at)
            VALUES (%s, %s, TRUE, now())
            ON CONFLICT (event_id, member_id) DO UPDATE SET checked_in = TRUE
            """,
            (event_id, member_id),
        )

    return _check


@pytest.fixture
def create_initiative(cursor, chapter_id):
    """Insert an initiative plus a chair row; returns the initiative id."""

    def _make(chair_member_id: str, *, title: str | None = None, chapter: str | None = None) -> str:
        chapter = chapter or chapter_id
        cursor.execute(
            """
            INSERT INTO initiatives (chapter_id, title, date, time, end_date, created_by)
            VALUES (%s, %s, '2026-04-01', '18:00', '2026-04-05', %s)
            RETURNING id
            """,
            (chapter, title or f"Initiative {uuid.uuid4().hex[:8]}", chair_member_id),
        )
        initiative_id = str(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO initiative_chairs (chapter_id, initiative_id, member_id, is_creator)
            VALUES (%s, %s, %s, TRUE)
            """,
            (chapter, initiative_id, chair_member_id),
        )
        return initiative_id

    return _make


@pytest.fixture
def create_job(cursor, chapter_id):
    """Insert a task the member committed to; returns the task id."""

    def _make(
        member_id: str,
        *,
        status: str = "approved",
        event_id: str | None = None,
        initiative_id: str | None = None,
        commitment_status: str = "active",
        chapter: str | None = None,
    ) -> str:
        chapter = chapter or chapter_id
        cursor.execute(
            """
            INSERT INTO tasks (chapter_id, title, status, event_id, initiative_id, approved_at)
            VALUES (%s, %s, %s, %s, %s, now())
            RETURNING id
            """,
            (chapter, f"Job {uuid.uuid4().hex[:8]}", status, event_id, initiative_id),
        )
        task_id = str(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO task_commitments (chapter_id, task_id, member_id, status)
            VALUES (%s, %s, %s, %s)
            """,
            (chapter, task_id, member_id, commitment_status),
        )
        return task_id

    return _make


# ── HTTP harness (mirrors tests/events/conftest.py) ──────────────────────────


@pytest.fixture
def app_on_test_db(sb_client, monkeypatch):
    """The real app, with contribution/rbac DB access pointed at the test DB."""
    import api.contribution.api.records as records_api
    import api.rbac.services.permissions as perm_mod

    monkeypatch.setattr(perm_mod, "get_db", lambda: sb_client)
    monkeypatch.setattr(records_api, "get_db", lambda: sb_client)

    from api.index import app

    return app


@pytest.fixture
def as_member(app_on_test_db, cursor):
    """Factory: a TestClient authenticated as the given member id."""
    from fastapi.testclient import TestClient

    from api.dependencies import get_current_user

    app = app_on_test_db

    def _factory(member_id: str):
        cursor.execute("SELECT * FROM members WHERE id = %s", (member_id,))
        member = {
            k: (str(v) if isinstance(v, uuid.UUID) else v)
            for k, v in dict(cursor.fetchone()).items()
        }

        async def _override():
            return member

        app.dependency_overrides[get_current_user] = _override
        return TestClient(app)

    yield _factory
    app.dependency_overrides.pop(get_current_user, None)
