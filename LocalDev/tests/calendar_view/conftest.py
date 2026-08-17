"""Calendar/instrumentation test harness.

Reuses the treasury DB fixtures (db_url, cursor, chapter_id, member_factory,
sb_client) plus the events-style role/user/event helpers, and mounts ONLY the
calendar + usage routers (other domains are not under test here).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
    """Create an event through the events service layer (visibility rules real)."""

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


@pytest.fixture
def invoice_factory(cursor, chapter_id):
    """Insert an open invoice directly (calendar only READS treasury)."""

    def _make(
        *,
        member_id: str,
        amount_cents: int = 2500,
        due_in_days: float | None = 10,
        status: str = "unpaid",
        kind: str = "dues",
        description: str | None = None,
    ) -> str:
        cursor.execute(
            """
            INSERT INTO unpaid_invoices
                (chapter_id, member_id, kind, amount_cents, status, description, due_at)
            VALUES (%s, %s, %s, %s, %s, %s,
                    CASE WHEN %s::numeric IS NULL THEN NULL
                         ELSE now() + %s::numeric * interval '1 day' END)
            RETURNING id
            """,
            (
                chapter_id,
                member_id,
                kind,
                amount_cents,
                status,
                description or f"Invoice {uuid.uuid4().hex[:8]}",
                due_in_days,
                due_in_days,
            ),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def task_factory(cursor, chapter_id):
    """Insert a task with an optional due date (calendar only READS tasks)."""

    def _make(
        *,
        title: str | None = None,
        due_on: str | None = "2026-07-10",
        event_id: str | None = None,
        status: str = "open",
    ) -> str:
        cursor.execute(
            """
            INSERT INTO tasks (chapter_id, title, status, event_id, due_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                chapter_id,
                title or f"Task {uuid.uuid4().hex[:8]}",
                status,
                event_id,
                f"{due_on}T17:00:00+00:00" if due_on else None,
            ),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def initiative_factory(cursor, chapter_id):
    """Insert an initiative directly (calendar only READS initiatives)."""

    def _make(
        *,
        title: str | None = None,
        date: str = "2026-07-01",
        time: str = "19:00",
        chairs: list[str] | None = None,
    ) -> str:
        cursor.execute(
            "INSERT INTO members (chapter_id, name, email, role, status) "
            "VALUES (%s, %s, %s, 'member', 'active') RETURNING id",
            (chapter_id, f"Creator {uuid.uuid4().hex[:8]}", f"{uuid.uuid4()}@test.local"),
        )
        creator = str(cursor.fetchone()["id"])
        cursor.execute(
            """
            INSERT INTO initiatives (chapter_id, title, date, time, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (chapter_id, title or f"Initiative {uuid.uuid4().hex[:8]}", date, time, creator),
        )
        initiative_id = str(cursor.fetchone()["id"])
        for member_id in chairs or [creator]:
            cursor.execute(
                "INSERT INTO initiative_chairs (chapter_id, initiative_id, member_id, is_creator) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (initiative_id, member_id) DO NOTHING",
                (chapter_id, initiative_id, member_id, member_id == creator),
            )
        return initiative_id

    return _make


@pytest.fixture
def grant_treasury_read(cursor, chapter_id):
    """Give a member chapter-wide treasury read access.

    0147 folded treasury_grants into the central catalog: read access is the
    `treasury_viewer` role (treasury:budget:view + treasury:audit:view), not a
    per-member capability row.
    """

    def _grant(member_id: str) -> None:
        cursor.execute(
            """
            INSERT INTO member_roles (chapter_id, member_id, role_key)
            VALUES (%s, %s, 'treasury_viewer')
            ON CONFLICT DO NOTHING
            """,
            (chapter_id, member_id),
        )

    return _grant


@pytest.fixture
def harness(sb_client, monkeypatch):
    """App with the calendar + usage routers; all DB access on the test DB."""
    import api.calendar.api.calendar as calendar_api
    import api.instrumentation.api.usage as usage_api
    import api.rbac.services.permissions as rbac_permissions
    from api.calendar.api.calendar import router as calendar_router
    from api.dependencies import get_current_user
    from api.instrumentation.api.usage import router as usage_router

    monkeypatch.setattr(calendar_api, "get_db", lambda: sb_client)
    monkeypatch.setattr(usage_api, "get_db", lambda: sb_client)
    monkeypatch.setattr(rbac_permissions, "get_db", lambda: sb_client)

    app = FastAPI()
    app.include_router(calendar_router, prefix="/api/calendar")
    app.include_router(usage_router, prefix="/api/usage")

    current_user: dict = {}
    app.dependency_overrides[get_current_user] = lambda: current_user

    client = TestClient(app)

    class Harness:
        def __init__(self):
            self.client = client

        def login(self, user: dict):
            current_user.clear()
            current_user.update(user)
            return client

    return Harness()
