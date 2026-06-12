"""Reuse the treasury DB harness fixtures (db_url, db_conn, cursor, chapter_id)."""

from __future__ import annotations

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
def create_event(sb_client):
    """Create an event through the service layer with sane defaults."""

    def _create(actor: dict, **overrides):
        from api.events.services import events as svc

        kwargs = dict(
            title="Test Event",
            date="2026-07-01",
            time="19:00",
            location="Chapter House",
        )
        kwargs.update(overrides)
        return svc.create_event(sb_client, actor=actor, **kwargs)

    return _create
