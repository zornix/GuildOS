"""Announcements SMS test harness.

Reuses the treasury DB fixtures (db_url, cursor, chapter_id, member_factory,
sb_client) and mounts the real FastAPI app with the announcements + rbac DB
boundaries monkeypatched onto the test database, so permission resolution and
the send path exercise the real seeded role/permission matrix.
"""

from __future__ import annotations

import uuid

import pytest

from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.fixture
def delivery_mode(monkeypatch):
    """Set settings.MESSAGE_DELIVERY_MODE (the single source of truth, not env).

    Delivery config moved from os.environ to api/config.py, so tests patch the
    settings attribute; monkeypatch.setenv no longer reaches the code path.
    """
    from api.config import settings

    def _set(mode: str) -> str:
        monkeypatch.setattr(settings, "MESSAGE_DELIVERY_MODE", mode)
        return mode

    _set("dry_run")
    return _set


@pytest.fixture
def app_on_test_db(sb_client, monkeypatch, delivery_mode):
    """The real app, with announcements/rbac DB access pointed at the test DB."""
    import api.announcements.api.announcements as ann_api
    import api.rbac.services.permissions as perm_mod

    monkeypatch.setattr(perm_mod, "get_db", lambda: sb_client)
    monkeypatch.setattr(ann_api, "get_db", lambda: sb_client)

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


@pytest.fixture
def give_role(cursor, chapter_id):
    """Assign a granular RBAC role (member_roles row) inside the test chapter."""

    def _give(member_id: str, role_key: str) -> None:
        cursor.execute(
            """
            INSERT INTO member_roles (chapter_id, member_id, role_key)
            VALUES (%s, %s, %s)
            ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING
            """,
            (chapter_id, member_id, role_key),
        )

    return _give


@pytest.fixture
def set_phone(cursor):
    def _set(member_id: str, phone: str | None) -> None:
        cursor.execute("UPDATE members SET phone = %s WHERE id = %s", (phone, member_id))

    return _set


@pytest.fixture
def announcement_factory(cursor, chapter_id):
    """Insert an announcement row directly (the in-app feed post already exists)."""

    def _make(
        *,
        status: str = "sent",
        audience: str = "chapter",
        title: str = "Chapter update",
        body: str = "Mandatory meeting at 7pm.",
    ) -> str:
        cursor.execute(
            """
            INSERT INTO announcements (chapter_id, title, body, audience, status, sent_at)
            VALUES (%s, %s, %s, %s, %s, CASE WHEN %s = 'sent' THEN now() END)
            RETURNING id
            """,
            (chapter_id, title, body, audience, status, status),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def president(member_factory, give_role, set_phone):
    m = member_factory()
    give_role(m, "president")
    set_phone(m, "+15550000001")
    return m


@pytest.fixture
def secretary(member_factory, give_role, set_phone):
    m = member_factory()
    give_role(m, "secretary")
    set_phone(m, "+15550000002")
    return m
