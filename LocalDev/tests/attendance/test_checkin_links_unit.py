"""Check-in link service logic against a fake supabase-shaped client (no DB).

Covers the three behaviors that are hard to reach through HTTP: which insert
failures count as a code collision, which attendance session governs a link,
and the chapter filter on the kill/list queries.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from api.attendance.services import checkin_links as svc

NOW = datetime.now(timezone.utc)


# ── a minimal stand-in for the supabase-py / PostgresClient surface ───────────

class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.op = None
        self.payload = None
        self.filters: dict = {}
        self.single_row = False

    def select(self, cols="*", **kw):
        self.op = "select"
        return self

    def insert(self, data):
        self.op, self.payload = "insert", data
        return self

    def update(self, data):
        self.op, self.payload = "update", data
        return self

    def eq(self, col, val):
        self.filters[col] = val
        return self

    def gte(self, col, val):
        return self

    def single(self):
        self.single_row = True
        return self

    def maybe_single(self):
        self.single_row = True
        return self

    def execute(self):
        self.client.queries.append(self)
        return self.client._run(self)


class FakeClient:
    """Records every query; replays scripted insert failures."""

    def __init__(self, *, insert_errors=None, sessions=None, link=None, links=None):
        self.insert_errors = list(insert_errors or [])
        self.sessions = sessions or []
        self.link = link
        self.links = links or []
        self.queries: list[FakeQuery] = []
        self.inserted: list[dict] = []

    def table(self, name):
        return FakeQuery(self, name)

    def _run(self, q: FakeQuery):
        if q.op == "insert":
            if self.insert_errors:
                raise self.insert_errors.pop(0)
            self.inserted.append(q.payload)
            return FakeResult([q.payload])
        if q.op == "update":
            return FakeResult([])
        if q.table_name == "attendance_sessions":
            rows = [s for s in self.sessions if s.get("event_id") == q.filters.get("event_id")]
            return FakeResult(rows)
        if q.table_name == "checkin_links":
            if q.single_row:
                return FakeResult(self.link)
            return FakeResult(self.links)
        return FakeResult([])


@pytest.fixture
def use_client(monkeypatch):
    def _use(client):
        monkeypatch.setattr(svc, "get_db", lambda: client)
        return client

    return _use


def unique_violation():
    from psycopg2 import errors

    return errors.UniqueViolation("duplicate key value violates unique constraint")


# ── _is_duplicate_code ────────────────────────────────────────────────────────

def test_psycopg2_unique_violation_is_a_collision():
    assert svc._is_duplicate_code(unique_violation())


def test_pgcode_attribute_is_a_collision():
    exc = Exception("nope")
    exc.pgcode = "23505"
    assert svc._is_duplicate_code(exc)


def test_apierror_shaped_code_is_a_collision():
    class APIError(Exception):
        code = "23505"

    assert svc._is_duplicate_code(APIError("insert failed"))


def test_duplicate_key_message_is_a_collision():
    assert svc._is_duplicate_code(Exception("duplicate key value violates unique constraint"))


@pytest.mark.parametrize(
    "exc",
    [
        Exception("connection reset by peer"),
        Exception("null value in column chapter_id violates not-null constraint"),
        ValueError("Unknown op: frobnicate"),
        TimeoutError("pool exhausted"),
    ],
)
def test_real_faults_are_not_collisions(exc):
    assert not svc._is_duplicate_code(exc)


def test_not_null_violation_is_not_a_collision():
    from psycopg2 import errors

    assert not svc._is_duplicate_code(errors.NotNullViolation("null value"))


# ── create_checkin_link retry policy ──────────────────────────────────────────

async def test_collision_is_retried_with_a_fresh_code(use_client):
    client = use_client(FakeClient(insert_errors=[unique_violation()]))
    result = await svc.create_checkin_link("ev-1", "officer-1")

    assert len(client.inserted) == 1
    assert result["short_code"] == client.inserted[0]["short_code"]
    assert result["event_id"] == "ev-1"


async def test_repeated_collisions_eventually_give_up(use_client):
    client = use_client(FakeClient(insert_errors=[unique_violation() for _ in range(5)]))
    with pytest.raises(HTTPException) as exc_info:
        await svc.create_checkin_link("ev-1", "officer-1")

    assert exc_info.value.status_code == 500
    assert client.inserted == []


async def test_a_real_error_fails_fast_instead_of_retrying(use_client):
    """The old bare `except Exception: continue` hid outages behind 5 retries."""
    client = use_client(FakeClient(insert_errors=[RuntimeError("connection reset")] * 5))
    with pytest.raises(HTTPException) as exc_info:
        await svc.create_checkin_link("ev-1", "officer-1")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Could not generate check-in code"
    inserts = [q for q in client.queries if q.op == "insert"]
    assert len(inserts) == 1, "a non-collision error must not be retried"


# ── _session_for_link ─────────────────────────────────────────────────────────

def _link(link_id="link-1", event_id="ev-1"):
    return {"id": link_id, "event_id": event_id}


def test_session_bound_to_this_link_governs():
    client = FakeClient(sessions=[
        {"id": "s-1", "event_id": "ev-1", "checkin_link_id": "link-1", "closes_at": None},
        {"id": "s-2", "event_id": "ev-1", "checkin_link_id": "link-9", "closes_at": None},
    ])
    assert svc._session_for_link(client, _link())["id"] == "s-1"


def test_single_unbound_session_governs_a_directly_created_link():
    client = FakeClient(sessions=[
        {"id": "s-1", "event_id": "ev-1", "checkin_link_id": None, "closes_at": None},
    ])
    assert svc._session_for_link(client, _link())["id"] == "s-1"


def test_session_bound_to_another_link_does_not_govern():
    """An old session's closed window must not kill a freshly opened link."""
    client = FakeClient(sessions=[
        {"id": "s-old", "event_id": "ev-1", "checkin_link_id": "link-old", "closes_at": None},
    ])
    assert svc._session_for_link(client, _link()) is None


def test_ambiguous_multiple_unbound_sessions_resolve_to_none():
    client = FakeClient(sessions=[
        {"id": "s-1", "event_id": "ev-1", "checkin_link_id": None, "closes_at": None},
        {"id": "s-2", "event_id": "ev-1", "checkin_link_id": None, "closes_at": None},
    ])
    assert svc._session_for_link(client, _link()) is None


def test_no_sessions_at_all_resolve_to_none():
    assert svc._session_for_link(FakeClient(sessions=[]), _link()) is None


# ── validate_checkin_link's closes_at gate ────────────────────────────────────

def _valid_link(session_id="s-1"):
    return {
        "id": "link-1",
        "event_id": "ev-1",
        "short_code": "A7x9Kp",
        "active": True,
        "events": {"id": "ev-1", "chapter_id": "ch-1", "title": "Meeting"},
    }


async def test_open_session_lets_the_link_through(use_client):
    use_client(FakeClient(
        link=_valid_link(),
        sessions=[{"id": "s-1", "event_id": "ev-1", "checkin_link_id": "link-1",
                   "closes_at": NOW + timedelta(minutes=30)}],
    ))
    link = await svc.validate_checkin_link("A7x9Kp")
    assert link is not None
    assert link["attendance_session"]["id"] == "s-1"


async def test_closed_session_kills_the_link(use_client):
    """closes_at was written by create_session and read by nothing."""
    use_client(FakeClient(
        link=_valid_link(),
        sessions=[{"id": "s-1", "event_id": "ev-1", "checkin_link_id": "link-1",
                   "closes_at": NOW - timedelta(minutes=1)}],
    ))
    assert await svc.validate_checkin_link("A7x9Kp") is None


async def test_closes_at_accepts_the_postgrest_string_form(use_client):
    use_client(FakeClient(
        link=_valid_link(),
        sessions=[{"id": "s-1", "event_id": "ev-1", "checkin_link_id": "link-1",
                   "closes_at": (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")}],
    ))
    assert await svc.validate_checkin_link("A7x9Kp") is None


async def test_session_without_closes_at_never_expires_the_link(use_client):
    use_client(FakeClient(
        link=_valid_link(),
        sessions=[{"id": "s-1", "event_id": "ev-1", "checkin_link_id": "link-1", "closes_at": None}],
    ))
    assert await svc.validate_checkin_link("A7x9Kp") is not None


async def test_unknown_code_is_none(use_client):
    use_client(FakeClient(link=None))
    assert await svc.validate_checkin_link("nope") is None


# ── tenant scoping on the write/read queries ──────────────────────────────────

async def test_deactivate_filters_on_chapter(use_client):
    client = use_client(FakeClient())
    await svc.deactivate_checkin_link("ev-1", "ch-1")

    update = next(q for q in client.queries if q.op == "update")
    assert update.filters["chapter_id"] == "ch-1"
    assert update.filters["event_id"] == "ev-1"
    assert update.filters["active"] is True


async def test_deactivate_requires_a_chapter():
    with pytest.raises(TypeError):
        await svc.deactivate_checkin_link("ev-1")  # type: ignore[call-arg]


async def test_list_active_links_filters_chapter_in_the_query(use_client):
    """The chapter filter must be in SQL, not a Python `continue`."""
    client = use_client(FakeClient(links=[
        {"event_id": "ev-1", "short_code": "AAA111", "expires_at": NOW.isoformat(),
         "events": {"title": "Meeting", "date": "2026-03-01", "chapter_id": "ch-1"}},
    ]))
    rows = await svc.list_active_links_for_chapter("ch-1")

    select = next(q for q in client.queries if q.op == "select")
    assert select.filters["chapter_id"] == "ch-1"
    assert [r["short_code"] for r in rows] == ["AAA111"]


# ── _as_datetime ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [None, "", "not a date", 42])
def test_unparseable_timestamps_are_none(value):
    assert svc._as_datetime(value) is None


def test_naive_datetime_is_treated_as_utc():
    naive = datetime(2026, 3, 1, 12, 0, 0)
    assert svc._as_datetime(naive).tzinfo is timezone.utc


def test_iso_string_with_z_suffix_parses():
    assert svc._as_datetime("2026-03-01T12:00:00Z") == datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
