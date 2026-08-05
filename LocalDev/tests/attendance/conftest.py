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


@pytest.fixture
def checkin_link_factory(cursor):
    """Insert an active check-in link for an event; returns its (id, short_code).

    chapter_id is left to the 0146 derive trigger, exactly as the app does.
    """

    def _make(event_id: str, *, minutes: int = 10, active: bool = True) -> tuple[str, str]:
        code = uuid.uuid4().hex[:6]
        cursor.execute(
            """
            INSERT INTO checkin_links (event_id, short_code, expires_at, active)
            VALUES (%s, %s, now() + make_interval(mins => %s), %s)
            RETURNING id, short_code
            """,
            (event_id, code, minutes, active),
        )
        row = cursor.fetchone()
        return str(row["id"]), row["short_code"]

    return _make


@pytest.fixture
def session_factory(cursor):
    """Insert an attendance session, optionally bound to a link and already closed."""

    def _make(chapter_id: str, event_id: str, *, checkin_link_id: str | None = None,
              closes_in_minutes: int | None = None) -> str:
        cursor.execute(
            """
            INSERT INTO attendance_sessions (chapter_id, event_id, mode, checkin_link_id, closes_at)
            VALUES (%s, %s, 'short_link', %s,
                    CASE WHEN %s IS NULL THEN NULL
                         ELSE now() + make_interval(mins => %s) END)
            RETURNING id
            """,
            (chapter_id, event_id, checkin_link_id, closes_in_minutes, closes_in_minutes),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def attendance_app(sb_client, monkeypatch):
    """The real app with the check-in DB boundaries pointed at the test DB."""
    import api.attendance.api.attendance as att_api
    import api.attendance.services.checkin_links as links_svc
    import api.events.api.events as events_api
    import api.rbac.services.permissions as perm_mod

    monkeypatch.setattr(att_api, "get_supabase", lambda: sb_client)
    monkeypatch.setattr(links_svc, "get_supabase_admin", lambda: sb_client)
    monkeypatch.setattr(events_api, "get_events_db", lambda: sb_client)
    monkeypatch.setattr(perm_mod, "get_rbac_db", lambda: sb_client)

    from api.index import app

    return app


@pytest.fixture
def anon_client(attendance_app):
    """Unauthenticated client — the check-in page and phone check-in take no JWT."""
    from fastapi.testclient import TestClient

    return TestClient(attendance_app)


@pytest.fixture
def as_member(attendance_app, cursor):
    """Factory: a TestClient authenticated as the given member id."""
    from fastapi.testclient import TestClient

    from api.dependencies import get_current_user

    app = attendance_app

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
