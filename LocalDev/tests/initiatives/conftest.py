"""Reuse the treasury DB harness fixtures (db_url, cursor, chapter_id, member_factory)
plus the events-style role/user helpers, and mount the real app for HTTP-level tests
(mirrors tests/events/conftest.py).
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


@pytest.fixture
def user_factory(chapter_id, member_factory):
    """Member dict shaped like api.dependencies.get_current_user output."""

    def _make(*, role: str = "member", chapter: str | None = None) -> dict:
        member_id = member_factory(role=role, chapter=chapter)
        return {"id": member_id, "chapter_id": chapter or chapter_id, "role": role}

    return _make


@pytest.fixture
def create_initiative(sb_client):
    """Create an initiative through the service layer with sane defaults."""

    def _create(actor: dict, **overrides):
        from api.initiatives.services import initiatives as svc

        kwargs = dict(
            title="Test Initiative",
            date="2026-07-01",
            time="19:00",
        )
        kwargs.update(overrides)
        return svc.create_initiative(sb_client, actor=actor, **kwargs)

    return _create


# ── HTTP harness (mirrors tests/events/conftest.py) ──────────────────────────


@pytest.fixture
def app_on_test_db(sb_client, monkeypatch):
    """The real app, with initiatives/tasks/rbac DB access pointed at the test DB."""
    import api.initiatives.api.initiatives as initiatives_api
    import api.rbac.services.permissions as perm_mod
    import api.tasks.api.tasks as tasks_api

    monkeypatch.setattr(perm_mod, "get_rbac_db", lambda: sb_client)
    monkeypatch.setattr(initiatives_api, "get_initiatives_db", lambda: sb_client)
    monkeypatch.setattr(tasks_api, "get_tasks_db", lambda: sb_client)

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
