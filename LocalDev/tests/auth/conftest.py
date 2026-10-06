"""Auth hardening test harness (migration 0148).

Reuses the treasury DB fixtures (db_url, cursor, chapter_id, member_factory) and
mounts the real FastAPI app with the auth + dependency DB boundaries pointed at
the test database, so login, token verification, setup codes, and rate limiting
all exercise the real code paths against real rows.

Two client flavors:
  * `client`      — no auth override; the real get_current_user runs, so token
                    signature/audience/epoch checks are genuinely exercised.
  * `as_member`   — factory overriding get_current_user with a member row, for
                    the officer-gated endpoints where plumbing a token adds
                    nothing (the announcements harness pattern).

Every client sends a unique X-Forwarded-For so per-IP rate-limit buckets never
leak between tests (and the XFF parsing gets covered for free).
"""

from __future__ import annotations

import uuid

import pytest

from tests.treasury.conftest import *  # noqa: F401,F403


@pytest.fixture
def auth_sb(db_url):
    """Postgres shim bound to the app's JWT secret, so tokens minted by the auth
    module verify through this client's auth shim."""
    from api.config import settings
    from api.platform.postgres import PostgresClient

    client = PostgresClient(db_url, settings.JWT_SECRET)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def app_on_test_db(auth_sb, db_url, monkeypatch):
    """The real app, with auth/dependency DB access pointed at the test DB."""
    import api.auth.api.auth as auth_api
    import api.dependencies as deps
    from api.config import settings

    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    monkeypatch.setattr(auth_api, "get_db", lambda: auth_sb)
    monkeypatch.setattr(deps, "get_db", lambda: auth_sb)

    from api.index import app

    return app


@pytest.fixture
def client(app_on_test_db):
    """Unauthenticated TestClient with a per-test source IP."""
    from fastapi.testclient import TestClient

    return TestClient(
        app_on_test_db,
        headers={"X-Forwarded-For": f"test-{uuid.uuid4()}"},
    )


@pytest.fixture
def as_member(app_on_test_db, cursor):
    """Factory: a TestClient carrying a real bearer token for the given member.

    Deliberately not a `dependency_overrides` entry: overrides install on the
    shared `api.index.app` singleton, so an override here also silently
    authenticated the `client` fixture above, which is supposed to run the real
    get_current_user. A genuine token keeps the two clients independent.
    """
    from fastapi.testclient import TestClient

    from api.auth.api.auth import _issue_member_token

    def _factory(member_id: str):
        cursor.execute("SELECT token_version FROM members WHERE id = %s", (member_id,))
        token = _issue_member_token(member_id, cursor.fetchone()["token_version"] or 0)
        return TestClient(
            app_on_test_db,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Forwarded-For": f"test-{uuid.uuid4()}",
            },
        )

    return _factory


@pytest.fixture
def member_factory(cursor, chapter_id):
    """Auth-local override of the treasury factory.

    The treasury factory mints `@test.local` addresses, which is fine for rows
    inserted straight into Postgres but not here: these tests drive the HTTP
    surface, and `EmailStr` rejects `.local` as a special-use domain (the
    request 422s before any auth logic runs). Members here get `@example.com`.
    Returns the member id, like the fixture it shadows.
    """

    def _make(
        *,
        role: str = "member",
        chapter: str | None = None,
        status: str = "active",
        email: str | None = None,
    ) -> str:
        cursor.execute(
            """
            INSERT INTO members (chapter_id, name, email, role, status)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                chapter or chapter_id,
                f"Member {uuid.uuid4().hex[:8]}",
                email or f"auth-{uuid.uuid4().hex}@example.com",
                role,
                status,
            ),
        )
        member_id = str(cursor.fetchone()["id"])
        if role == "officer":
            # Since 0162 members.role is display-only; an officer is a member_roles row.
            cursor.execute(
                """
                INSERT INTO member_roles (chapter_id, member_id, role_key)
                VALUES (%s, %s, 'officer')
                ON CONFLICT (member_id, role_key, chapter_id) DO NOTHING
                """,
                (chapter or chapter_id, member_id),
            )
        return member_id

    return _make


@pytest.fixture
def unknown_email() -> str:
    """An address no member holds, fresh per test.

    Never a hardcoded literal: failed logins are rate-limited per email over a
    15-minute window, and login_attempts rows outlive the pytest session, so a
    shared literal trips 429 once the suite is run a few times in a row.
    """
    return f"nobody-{uuid.uuid4().hex}@example.com"


@pytest.fixture
def member_email(cursor):
    """Read a member's email (member_factory only hands back the id)."""

    def _get(member_id: str) -> str:
        cursor.execute("SELECT email FROM members WHERE id = %s", (member_id,))
        return cursor.fetchone()["email"]

    return _get


@pytest.fixture
def set_password_hash(cursor):
    """Give a member a real bcrypt password hash, straight into the row."""
    from api.auth.api.auth import _hash_secret

    def _set(member_id: str, password: str) -> None:
        cursor.execute(
            "UPDATE members SET password_hash = %s WHERE id = %s",
            (_hash_secret(password), member_id),
        )

    return _set


@pytest.fixture
def set_status(cursor):
    def _set(member_id: str, status: str) -> None:
        cursor.execute("UPDATE members SET status = %s WHERE id = %s", (status, member_id))

    return _set


@pytest.fixture
def token_version(cursor):
    def _get(member_id: str) -> int:
        cursor.execute("SELECT token_version FROM members WHERE id = %s", (member_id,))
        return cursor.fetchone()["token_version"]

    return _get


@pytest.fixture
def issue_code(cursor, chapter_id):
    """Insert a setup code row directly, with control over expiry/use."""
    from api.auth.api.auth import _hash_secret

    def _issue(member_id: str, code: str, *, expires_in_days: float = 7, used: bool = False) -> str:
        cursor.execute(
            """
            INSERT INTO member_setup_codes
                (chapter_id, member_id, code_hash, expires_at, used_at)
            VALUES (%s, %s, %s, now() + (%s || ' days')::interval,
                    CASE WHEN %s THEN now() END)
            RETURNING id
            """,
            (chapter_id, member_id, _hash_secret(code), str(expires_in_days), used),
        )
        return str(cursor.fetchone()["id"])

    return _issue


@pytest.fixture
def burn_attempts(cursor):
    """Pre-load failed login attempts for an email, inside the 15-minute window."""

    def _burn(email: str, count: int) -> None:
        for _ in range(count):
            cursor.execute(
                "INSERT INTO login_attempts (email, ip, success) VALUES (%s, %s, FALSE)",
                (email, f"test-{uuid.uuid4()}"),
            )

    return _burn


@pytest.fixture
def burn_ip_attempts(cursor):
    """Pre-load failed attempts for one source IP, across distinct emails."""

    def _burn(ip: str, count: int) -> None:
        for _ in range(count):
            cursor.execute(
                "INSERT INTO login_attempts (email, ip, success) VALUES (%s, %s, FALSE)",
                (f"spray-{uuid.uuid4().hex}@example.com", ip),
            )

    return _burn
