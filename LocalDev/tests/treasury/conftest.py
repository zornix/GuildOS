"""Treasury test harness — frozen contract §2.8 of the orchestration plan.

- Opens a direct psycopg2 connection to TEST_DATABASE_URL (defaults to SUPABASE_DB_URL)
  for raw-SQL / trigger / RPC tests. This connection is a Postgres superuser and
  therefore BYPASSES RLS — it is for trigger/RPC/atomicity tests only. RLS policy
  tests use supabase-py with a member JWT (see test_chunk0_rls.py), never this fixture.
- Provides a FakeClock fixture and a per-test `chapter_id` fixture that inserts a fresh
  chapters row, so every assertion is chapter-scoped (the shared demo's append-only
  tables — big_ledger, audit_logs — accumulate and cannot be truncated; §3.4).
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.db_guard import ProdGuardError, require_demo


def _load_dotenv_value(*keys: str) -> str | None:
    """Resolve a key from the process env, falling back to LocalDev/.env.

    Tests are run as `python -m pytest` without `set -a`, so .env values are not
    automatically exported. We read them directly rather than depend on python-dotenv.
    """
    for k in keys:
        v = os.environ.get(k)
        if v:
            return v
    env_path = _REPO_ROOT / ".env"
    if env_path.is_file():
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, val = line.partition("=")
            if name.strip() in keys and val.strip():
                return val.strip()
    return None


def _test_database_url() -> str | None:
    return _load_dotenv_value("TEST_DATABASE_URL", "SUPABASE_DB_URL")


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_database_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL / SUPABASE_DB_URL not set — DB-backed tests skipped")
    try:
        require_demo(url, context="pytest")
    except ProdGuardError as exc:
        # Stop the whole session before ANY test opens a connection — a test
        # run against prod would write permanent rows into append-only tables.
        pytest.exit(str(exc), returncode=1)
    return url


@pytest.fixture
def db_conn(db_url):
    """Function-scoped autocommit psycopg2 connection (superuser; bypasses RLS)."""
    conn = psycopg2.connect(db_url, connect_timeout=15)
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def cursor(db_conn):
    with db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        yield cur


@pytest.fixture
def fake_clock():
    from api.treasury.core.clock import FakeClock

    return FakeClock(datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc))


@pytest.fixture
def chapter_id(cursor) -> str:
    """Insert a fresh chapter per test; assertions stay scoped to it (§3.4).

    No teardown: big_ledger/audit_logs rows reference chapter_id and are DELETE-blocked
    by trigger, so the chapter cannot be removed once exercised. Accumulation on the
    demo is expected and tolerated because every assertion is chapter-scoped.
    """
    cursor.execute(
        """
        INSERT INTO chapters (name, organization, school)
        VALUES (%s, 'Treasury Test Org', 'Test University')
        RETURNING id
        """,
        (f"tr-test-{uuid.uuid4()}",),
    )
    return str(cursor.fetchone()["id"])


@pytest.fixture
def member_factory(cursor, chapter_id):
    """Factory inserting a member into the test chapter (unique email). Returns member id."""

    def _make(*, role: str = "member", chapter: str | None = None) -> str:
        cursor.execute(
            """
            INSERT INTO members (chapter_id, name, email, role, status)
            VALUES (%s, %s, %s, %s, 'active')
            RETURNING id
            """,
            (chapter or chapter_id, f"Member {uuid.uuid4().hex[:8]}", f"{uuid.uuid4()}@test.local", role),
        )
        return str(cursor.fetchone()["id"])

    return _make


@pytest.fixture
def member_id(member_factory) -> str:
    return member_factory()


@pytest.fixture
def sb_client(db_url):
    """A supabase-like client (the psycopg shim) pointed at the test DB.

    This is the SAME `.table(...)` / `.rpc(...)` interface the app uses in production
    (supabase-py) and offline (PostgresClient shim), so writer tests exercise the real
    write path rather than raw SQL. Connects as the DB superuser (bypasses RLS).
    """
    from api.postgres_client import PostgresClient

    client = PostgresClient(db_url)
    try:
        yield client
    finally:
        client.close()
