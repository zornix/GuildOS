"""Chapter onboarding harness (#74).

Reuses the auth harness (which reuses treasury's DB fixtures) and additionally
points `api/chapters` at the test database. Everything these tests create is
named with a uuid and torn down at the end of the test, because the suite runs
against the shared demo DB alongside other agents.
"""

from __future__ import annotations

import uuid

import pytest

from tests.auth.conftest import *  # noqa: F401,F403


@pytest.fixture
def app_on_test_db(auth_sb, db_url, monkeypatch):
    """The real app with auth, dependencies AND chapters bound to the test DB."""
    import api.auth.api.auth as auth_api
    import api.chapters.api.chapters as chapters_api
    import api.dependencies as deps
    from api.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    monkeypatch.setattr(auth_api, "get_db", lambda: auth_sb)
    monkeypatch.setattr(deps, "get_db", lambda: auth_sb)
    monkeypatch.setattr(chapters_api, "get_db", lambda: auth_sb)

    from api.index import app

    return app


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """The bootstrap limiter is process-global; a shared window would make test
    order load-bearing."""
    from api.chapters import auth as chapters_auth

    chapters_auth._recent.clear()
    yield
    chapters_auth._recent.clear()


@pytest.fixture
def cleanup(cursor):
    """Delete chapters (members/roles/codes cascade) and stray members at teardown."""
    chapter_ids: list[str] = []
    emails: list[str] = []
    yield {"chapters": chapter_ids, "emails": emails}
    if emails:
        cursor.execute("DELETE FROM members WHERE email = ANY(%s)", (emails,))
    for cid in chapter_ids:
        cursor.execute("DELETE FROM chapters WHERE id = %s", (cid,))


@pytest.fixture
def unique():
    """uuid-suffixed names/emails — other agents run this suite concurrently."""

    def _make(prefix: str = "") -> str:
        return f"{prefix}{uuid.uuid4().hex[:12]}"

    return _make


@pytest.fixture
def create_body(unique):
    def _make(**overrides) -> dict:
        body = {
            "name": f"Chapter {unique()}",
            "organization": "TKE",
            "school": "State University",
            "officer_name": "Jane Roe",
            "officer_email": f"officer-{unique()}@example.com",
            "officer_phone": "+15551110001",
        }
        body.update(overrides)
        return body

    return _make


@pytest.fixture
def csv_bytes():
    def _make(rows: list[str], header: str = "name,email,phone") -> bytes:
        return ("\n".join([header, *rows]) + "\n").encode("utf-8")

    return _make
