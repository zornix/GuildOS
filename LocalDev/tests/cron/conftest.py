"""Cron test harness.

Reuses the treasury DB fixtures (db_url, db_conn, cursor, chapter_id,
member_factory, sb_client) per the tests/rbac/conftest.py pattern, and mounts the
real FastAPI app with the outbox drain pointed at the test database per the
tests/announcements pattern.
"""

from __future__ import annotations

import pytest

from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.fixture
def delivery_mode(monkeypatch):
    """Set settings.MESSAGE_DELIVERY_MODE (the source of truth, not env)."""
    from api.config import settings

    def _set(mode: str) -> str:
        monkeypatch.setattr(settings, "MESSAGE_DELIVERY_MODE", mode)
        return mode

    _set("dry_run")
    return _set


@pytest.fixture
def cron_secret(monkeypatch):
    """Set settings.CRON_SECRET; returns the configured value."""
    from api.config import settings

    def _set(secret: str) -> str:
        monkeypatch.setattr(settings, "CRON_SECRET", secret)
        return secret

    _set("test-cron-secret")
    return _set


@pytest.fixture
def cron_client(sb_client, monkeypatch, delivery_mode, cron_secret):
    """TestClient on the real app, with the drain's DB client on the test DB."""
    from fastapi.testclient import TestClient

    import api.cron.services.outbox_drain as drain_mod

    monkeypatch.setattr(drain_mod, "_resolve_sb", lambda sb=None: sb or sb_client)

    from api.index import app

    return TestClient(app)


@pytest.fixture
def auth_header(cron_secret):
    """The header Vercel Cron sends for the currently configured secret."""

    def _header(secret: str | None = None):
        from api.config import settings

        return {"Authorization": f"Bearer {secret or settings.CRON_SECRET}"}

    return _header


@pytest.fixture
def outbox_row(cursor, chapter_id):
    """Insert one message_outbox row directly and return it as a dict."""
    import json

    def _make(
        *,
        event_type: str = "JOB_REPORTED",
        member_id: str | None = None,
        target_table: str = "tasks",
        target_id: str | None = None,
        payload: dict | None = None,
        status: str = "pending",
        delivery_mode: str = "dry_run",
        dedup_key: str | None = None,
    ) -> dict:
        import uuid as _uuid

        cursor.execute(
            """
            INSERT INTO message_outbox
                (chapter_id, event_type, member_id, target_table, target_id,
                 dedup_key, payload, status, delivery_mode)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            RETURNING *
            """,
            (
                chapter_id,
                event_type,
                member_id,
                target_table,
                target_id or str(_uuid.uuid4()),
                dedup_key or f"{event_type}:{_uuid.uuid4()}",
                json.dumps(payload or {}),
                status,
                delivery_mode,
            ),
        )
        return dict(cursor.fetchone())

    return _make


@pytest.fixture
def read_outbox(cursor):
    def _read(row_id) -> dict:
        cursor.execute("SELECT * FROM message_outbox WHERE id = %s", (row_id,))
        return dict(cursor.fetchone())

    return _read
