"""Shared fixtures/helpers for the TREASURY V1 test files (no tests here).

Endpoint tests run the real FastAPI app with:
- `get_current_user` overridden to a canned member dict, and
- the process-wide PostgresClient pointed at the test DB (so rbac permission
  resolution, treasury services and RPCs all hit TEST_DATABASE_URL).
"""

from __future__ import annotations

import pytest


def make_user(member_id: str, chapter_id: str, role: str = "member") -> dict:
    """A canned get_current_user payload (shape of a members row)."""
    return {
        "id": member_id,
        "chapter_id": chapter_id,
        "role": role,
        "name": "V1 Test User",
        "email": f"{member_id}@test.local",
        "status": "active",
    }


def assign_role(cursor, chapter_id: str, member_id: str, role_key: str) -> None:
    """Grant an rbac role by inserting a member_roles row (see tests/rbac)."""
    cursor.execute(
        """
        INSERT INTO member_roles (chapter_id, member_id, role_key)
        VALUES (%s, %s, %s)
        ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING
        """,
        (chapter_id, member_id, role_key),
    )


@pytest.fixture
def api(sb_client, monkeypatch):
    """Factory: api(user) -> TestClient acting as that user, on the test DB."""
    import api.db as db_mod

    monkeypatch.setattr(db_mod, "_pg_client", sb_client)

    from fastapi.testclient import TestClient

    from api.dependencies import get_current_user
    from api.index import app

    def _as(user: dict) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield _as
    app.dependency_overrides.pop(get_current_user, None)
