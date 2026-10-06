"""Check-in link service logic against a fake supabase-shaped client (no DB).

Covers the three behaviors that are hard to reach through HTTP: which insert
failures count as a code collision, which attendance session governs a link,
and the chapter filter on the kill/list queries.
"""

from __future__ import annotations

from contextlib import contextmanager
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

    @contextmanager
    def transaction(self):
        yield self

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

    return errors.UniqueViolation('duplicate key value violates unique constraint "checkin_links_short_code_key"')


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


async def test_ambiguous_multiple_unbound_sessions_invalidate_the_link(use_client):
    use_client(FakeClient(link=_valid_link(), sessions=[
        {"id": "s-1", "event_id": "ev-1", "checkin_link_id": None, "closes_at": None},
        {"id": "s-2", "event_id": "ev-1", "checkin_link_id": None, "closes_at": None},
    ]))
    assert await svc.validate_checkin_link("A7x9Kp") is None


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


@pytest.mark.parametrize("closed", [False, True])
async def test_two_sessions_bound_to_one_link_is_invalid_even_before_close(use_client, closed):
    closes_at = NOW - timedelta(minutes=1) if closed else None
    use_client(FakeClient(link=_valid_link(), sessions=[
        {"id": "s-1", "event_id": "ev-1", "checkin_link_id": "link-1", "closes_at": closes_at},
        {"id": "s-2", "event_id": "ev-1", "checkin_link_id": "link-1", "closes_at": closes_at},
    ]))
    assert await svc.validate_checkin_link("A7x9Kp") is None


async def test_link_with_no_session_at_all_is_valid_until_ttl(use_client):
    use_client(FakeClient(link=_valid_link(), sessions=[]))
    assert await svc.validate_checkin_link("A7x9Kp") is not None


def test_several_open_unbound_sessions_are_not_bound():
    client = FakeClient(sessions=[
        {"id": "s-1", "event_id": "ev-1", "checkin_link_id": None, "closes_at": None},
        {"id": "s-2", "event_id": "ev-1", "checkin_link_id": None, "closes_at": None},
    ])
    svc._bind_open_sessions(client, "ev-1", "link-1", NOW)
    assert not any(q.op == "update" for q in client.queries)


async def test_failed_link_insert_keeps_the_old_link_active(attendance_app, cursor, event_factory, chapter_id, member_factory, monkeypatch):
    event = event_factory(chapter_id)
    actor = member_factory(role="officer")
    old_link = await svc.create_checkin_link(event, actor)
    # short_code is TEXT, so force a NOT NULL violation instead of a length error.
    monkeypatch.setattr(svc, "generate_short_code", lambda: None)
    with pytest.raises(HTTPException) as exc:
        await svc.create_checkin_link(event, actor)
    assert exc.value.status_code == 500
    cursor.execute("SELECT active FROM checkin_links WHERE event_id = %s AND short_code = %s", (event, old_link["short_code"]))
    assert cursor.fetchone()["active"] is True


async def test_link_session_does_not_double_bind(attendance_app, sb_client, cursor, event_factory, chapter_id, member_factory, session_factory):
    from api.attendance.services.sessions import create_session
    event = event_factory(chapter_id)
    actor = member_factory(role="officer")
    manual = session_factory(chapter_id, event, mode="manual")
    session = await create_session(sb_client, chapter_id=chapter_id, event_id=event, mode="short_link", closes_at=None, actor_id=actor)
    cursor.execute("SELECT id FROM attendance_sessions WHERE event_id = %s AND checkin_link_id = %s", (event, session["checkin_link_id"]))
    assert [str(row["id"]) for row in cursor.fetchall()] == [session["id"]]
    cursor.execute("SELECT checkin_link_id FROM attendance_sessions WHERE id = %s", (manual,))
    assert cursor.fetchone()["checkin_link_id"] is None
    assert await svc.validate_checkin_link(session["checkin_link"]["short_code"]) is not None


async def test_failed_session_insert_leaves_no_link(attendance_app, sb_client, cursor, event_factory, chapter_id, member_factory, monkeypatch):
    from api.attendance.services.sessions import create_session
    from api.platform.postgres import _TableAccessor
    import psycopg2
    event = event_factory(chapter_id)
    actor = member_factory(role="officer")
    original_insert = _TableAccessor.insert

    def invalid_session_insert(query, data):
        if query._table == "attendance_sessions":
            data = {**data, "mode": "invalid"}
        return original_insert(query, data)

    monkeypatch.setattr(_TableAccessor, "insert", invalid_session_insert)
    with pytest.raises(psycopg2.errors.CheckViolation):
        await create_session(sb_client, chapter_id=chapter_id, event_id=event, mode="short_link", closes_at=None, actor_id=actor)
    cursor.execute("SELECT id FROM checkin_links WHERE event_id = %s", (event,))
    assert cursor.fetchall() == []
    cursor.execute("SELECT linked_attendance_session_id FROM events WHERE id = %s", (event,))
    assert cursor.fetchone()["linked_attendance_session_id"] is None


def test_one_active_link_per_event_is_enforced_by_the_database(cursor, event_factory, chapter_id, checkin_link_factory):
    import psycopg2
    event = event_factory(chapter_id)
    checkin_link_factory(event)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        checkin_link_factory(event)


async def test_active_link_collision_returns_conflict_without_retry(use_client):
    from types import SimpleNamespace
    from psycopg2 import errors
    error = errors.UniqueViolation("duplicate key")
    # psycopg2's diag is read-only; use the same structured error surface.
    class ActiveLinkCollision(Exception):
        pgcode = "23505"
        diag = SimpleNamespace(constraint_name="uq_checkin_links_one_active_per_event")
    client = use_client(FakeClient(insert_errors=[ActiveLinkCollision(), error]))
    with pytest.raises(HTTPException) as exc:
        await svc.create_checkin_link("ev-1", "officer-1")
    assert exc.value.status_code == 409
    assert len([q for q in client.queries if q.op == "insert"]) == 1


async def test_unknown_unique_constraint_is_not_retried(use_client):
    client = use_client(FakeClient(insert_errors=[Exception('duplicate key value violates unique constraint "unrelated_key"')]))
    with pytest.raises(HTTPException) as exc:
        await svc.create_checkin_link("ev-1", "officer-1")
    assert exc.value.status_code == 500
    assert len([q for q in client.queries if q.op == "insert"]) == 1


async def test_code_collision_retries_the_whole_transaction(attendance_app, cursor, chapter_id, event_factory, member_factory, monkeypatch):
    import uuid
    actor = member_factory(role="officer")
    first_event = event_factory(chapter_id)
    second_event = event_factory(chapter_id)
    existing = await svc.create_checkin_link(first_event, actor)
    previous = await svc.create_checkin_link(second_event, actor)
    codes = iter([existing["short_code"], uuid.uuid4().hex[:6]])
    monkeypatch.setattr(svc, "generate_short_code", lambda: next(codes))
    replacement = await svc.create_checkin_link(second_event, actor)
    cursor.execute("SELECT id, active FROM checkin_links WHERE event_id = %s", (second_event,))
    states = {str(row["id"]): row["active"] for row in cursor.fetchall()}
    assert states == {previous["id"]: False, replacement["id"]: True}
    cursor.execute("SELECT active FROM checkin_links WHERE id = %s", (existing["id"],))
    assert cursor.fetchone()["active"] is True


def test_rpc_http_error_mappings():
    from api.attendance.api.errors import _rpc_http_error

    # not found -> 404
    e404 = _rpc_http_error(Exception("event 123 not found in chapter 456"))
    assert e404.status_code == 404
    assert e404.detail == "Event not found"

    # member not found -> 404
    m404 = _rpc_http_error(Exception("member 123 not found in chapter 456"))
    assert m404.status_code == 404
    assert m404.detail == "Member not found"

    # not active -> 403
    e403 = _rpc_http_error(Exception("actor 123 is not an active member of chapter 456"))
    assert e403.status_code == 403
    assert e403.detail == "Actor is not an active member of this chapter"

    # excuse reason required -> 400
    e400 = _rpc_http_error(Exception("excuse reason is required when marking as excused"))
    assert e400.status_code == 400
    assert e400.detail == "Excuse reason is required when marking as excused"

    # unknown -> 400 default safe message
    unknown = _rpc_http_error(Exception("internal plpgsql syntax error at line 42"))
    assert unknown.status_code == 400
    assert unknown.detail == "That change is not allowed"


def test_rpc_http_error_keeps_main_status_rules_for_already_checked_in():
    from api.attendance.api.errors import _rpc_http_error

    assert _rpc_http_error(Exception("already checked in")).status_code == 400


def test_rpc_http_error_does_not_read_bare_words_as_not_found():
    from api.attendance.api.errors import _rpc_http_error

    fk = _rpc_http_error(Exception(
        'insert or update on table "event_attendance" violates foreign key '
        'constraint "event_attendance_member_id_fkey"'
    ))
    assert fk.status_code == 400
    assert fk.detail == "That change is not allowed"

    # The PL/pgSQL CONTEXT line names the function; that must not pick the message.
    review = _rpc_http_error(Exception(
        "excuse 9f not found in chapter 4a\n"
        "CONTEXT:  PL/pgSQL function at_review_excuse(uuid,uuid,text,uuid,text) line 20 at RAISE"
    ))
    assert review.status_code == 404
    assert review.detail == "Excuse not found"
    odd = _rpc_http_error(Exception(
        "deadlock detected\nCONTEXT:  PL/pgSQL function at_review_excuse(uuid) line 3"
    ))
    assert odd.detail == "That change is not allowed"
