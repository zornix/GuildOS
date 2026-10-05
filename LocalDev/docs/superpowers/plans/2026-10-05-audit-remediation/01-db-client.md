# 01 · DB client: transactions, fail-fast joins, safe identifiers

> **For agentic workers:** read `00-README.md` first; its rules bind every step here. Steps use checkbox (`- [ ]`) syntax. Work task by task, test first.

**Stream:** `01-db-client` · **Wave:** 1 · **Agent:** Claude Opus 5.5 (worktree agent) · **Branch:** `fix/audit-01-db-client`
**Findings:** F-011 (helper only), F-021, F-026, F-039, R-03, R-04
**Goal:** give the one database client a real transaction, stop it silently dropping joins, validate identifiers, and stop converting `Decimal` to `float`.
**Architecture:** everything lives in `api/platform/postgres.py`. A transaction is a second `PostgresClient` bound to one pooled connection with `autocommit=False`; the builders already take their connection from `self._pool`, so the transaction hands them a one-connection stand-in. No caller changes in this stream: wave 2 streams adopt `transaction()` in their own domains.
**Spec:** `docs/audit/2026-09-30-forensic-audit.md` cards F-011, F-026, F-039 and Appendix C.4 (R-03, R-04).

## Global constraints

- Only these files may change: `api/platform/postgres.py`, `api/platform/outbox.py`, `api/treasury/notifications.py` (docstring only), `tests/platform/__init__.py` (new, empty), `tests/platform/conftest.py` (new), `tests/platform/test_*.py` (new), existing outbox tests that asserted the old swallow-everything behaviour, `tests/tasks/test_commitments_api.py` (one added test).
- No migration. No new dependency. The public builder surface (`table().select/insert/update/delete/upsert`, `rpc()`, `QueryResult`) keeps its shape.
- Do not touch `_ARRAY_TYPED_RPC_PARAMS`, `_LocalAuth`, `FK_MAP` contents, or `JOIN_STAR_COLUMNS` contents.
- This stream may run the full backend suite once, at the end (Task 6). It takes about 11 minutes.

## Review focus

1. A transaction that raises must leave the pooled connection clean (`autocommit=True`, no open transaction) for the next request.
2. `BaseException` (including `KeyboardInterrupt`, `asyncio.CancelledError`) inside a transaction must roll back.
3. Code inside `with db.transaction()` that calls a helper using `get_db()` writes outside the transaction. The helper cannot detect this; the contract in Task 2 documents it.
4. Identifier validation must not reject any select string that exists in `api/` today (run the full suite).
5. A `RETURNING` row with a `NUMERIC` column now carries `Decimal`; anything that `json.dumps` such a row breaks.

---

### Task 1: F-026 — prove ids are strings (expected: no code change)

The audit card says SELECT rows carry `uuid.UUID` ids, so `member_id != user["id"]` is always true for a string from the client. A live check on 2026-10-05 showed SELECT returns `str` (psycopg2 2.9.11, no `register_uuid` in the repo). This task pins that with tests. If both tests pass on the untouched branch, record F-026 as `NOT_REPRODUCED` and change no production code.

**Files:**
- Create: `tests/platform/__init__.py` (empty), `tests/platform/conftest.py`, `tests/platform/test_id_types.py`
- Modify: `tests/tasks/test_commitments_api.py` (append one test)

- [ ] **Step 1: conftest**

```python
"""Reuse the treasury DB harness fixtures (db_url, cursor, chapter_id, member_factory, sb_client)."""
from tests.treasury.conftest import *  # noqa: F401,F403
```

- [ ] **Step 2: write the tests**

`tests/platform/test_id_types.py`:

```python
def test_select_returns_string_ids(sb_client, member_id, chapter_id):
    row = sb_client.table("members").select("id, chapter_id").eq("id", member_id).single().execute().data
    assert isinstance(row["id"], str) and row["id"] == member_id
    assert isinstance(row["chapter_id"], str) and row["chapter_id"] == chapter_id
```

In `tests/tasks/test_commitments_api.py`, read the existing `harness` fixture and the nearest existing self-commit test, then add `test_member_can_commit_self_with_explicit_string_id`: a member without `tasks:assign` POSTs `/{task_id}/commit` with body `{"member_id": "<their own id as str>"}` and gets 200. Build the current-user override the same way the neighbouring tests do, but load the user row through `sb_client.table("members").select("*, chapters(*)")` so its `id` has the production type.

- [ ] **Step 3: run**

Run: `python3 -m pytest tests/platform/test_id_types.py tests/tasks/test_commitments_api.py -q`
Expected: PASS on the untouched branch. If so, F-026 = `NOT_REPRODUCED`; keep the tests.
If either FAILS: the finding is real. Fix it by comparing `str(a) != str(b)` at `api/tasks/api/commitments.py:46-48` and `:73-75`, `api/events/services/events.py:700-706` and `:732-741`, `api/attendance/api/summary.py:35-36` (these three files then join your allowed list; say so in the report).

- [ ] **Step 4: commit** — `test(platform): pin id types returned by the DB client`

---

### Task 2: F-011 — `PostgresClient.transaction()`

**Files:**
- Modify: `api/platform/postgres.py` (`QueryBuilder.execute` ~169-186, `_RpcBuilder.execute` ~536-544, `PostgresClient`)
- Test: `tests/platform/test_transaction.py`

**Interfaces (produced, used by wave 2 streams):**

```python
with get_db().transaction() as tx:      # tx is a PostgresClient bound to ONE connection
    tx.table("events").update({...}).eq("id", event_id).execute()
    call_rpc("ev_set_audience", {...}, sb=tx)
# commit on normal exit; rollback and re-raise on any exception
```

Rules for callers: (1) every helper called inside the block must take the client as a parameter and use it; a helper that calls `get_db()` itself runs outside the transaction. (2) Never catch a database error inside the block and carry on: the transaction is already aborted, and exit raises `RuntimeError`. (3) "Insert unless it exists" inside a transaction must use `insert(..., ignore_conflict=...)` (Task 6), never try/except on a unique violation.

- [ ] **Step 1: write the failing tests**

```python
import uuid
import pytest
from api.platform.rpc import call_rpc


def _name():
    return f"tx-test-{uuid.uuid4()}"


def _exists(sb, name):
    return bool(sb.table("chapters").select("id").eq("name", name).execute().data)


def test_commit_on_success(sb_client):
    a, b = _name(), _name()
    with sb_client.transaction() as tx:
        tx.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
        tx.table("chapters").insert({"name": b, "organization": "t", "school": "t"}).execute()
    assert _exists(sb_client, a) and _exists(sb_client, b)


def test_rollback_on_error(sb_client):
    a = _name()
    with pytest.raises(RuntimeError):
        with sb_client.transaction() as tx:
            tx.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
            raise RuntimeError("boom")
    assert not _exists(sb_client, a)


def test_uncommitted_rows_invisible_outside(sb_client):
    a = _name()
    with sb_client.transaction() as tx:
        tx.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
        assert _exists(tx, a)
        assert not _exists(sb_client, a)
    assert _exists(sb_client, a)


def test_rpc_joins_the_transaction(sb_client, chapter_id, member_factory):
    actor = member_factory(role="officer")
    target = member_factory()
    with pytest.raises(RuntimeError):
        with sb_client.transaction() as tx:
            call_rpc("rbac_assign_role", {
                "p_chapter_id": chapter_id, "p_member_id": target,
                "p_role_key": "secretary", "p_actor_id": actor,
            }, sb=tx)
            raise RuntimeError("boom")
    rows = sb_client.table("member_roles").select("id").eq("member_id", target).execute().data
    assert rows == []


def test_swallowed_db_error_cannot_commit_silently(sb_client):
    """Postgres aborts the transaction on any failed statement. If the caller swallows that
    error, COMMIT would quietly become ROLLBACK and the caller would think it saved."""
    a = _name()
    with pytest.raises(RuntimeError, match="aborted"):
        with sb_client.transaction() as tx:
            tx.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
            try:
                tx.table("chapters").insert({"no_such_column": 1}).execute()
            except Exception:
                pass                                   # the swallow
    assert not _exists(sb_client, a)


def test_connection_is_clean_after_rollback(sb_client):
    with pytest.raises(RuntimeError):
        with sb_client.transaction():
            raise RuntimeError("boom")
    a = _name()
    # a plain call after a failed transaction still autocommits
    sb_client.table("chapters").insert({"name": a, "organization": "t", "school": "t"}).execute()
    assert _exists(sb_client, a)
```

- [ ] **Step 2: run, expect FAIL** — `python3 -m pytest tests/platform/test_transaction.py -q` → `AttributeError: 'PostgresClient' object has no attribute 'transaction'`

- [ ] **Step 3: implement**

Add near the top of `postgres.py` (after imports) and to `PostgresClient`:

```python
from contextlib import contextmanager


class _TxPool:
    """Stands in for the pool inside a transaction: always the same connection."""

    in_tx = True

    def __init__(self, conn):
        self._conn = conn

    def getconn(self):
        return self._conn

    def putconn(self, conn):
        pass
```

```python
    # in PostgresClient
    @contextmanager
    def transaction(self):
        """One connection, one transaction. Commit on exit, roll back on any error.

        Yields a client bound to that connection; pass it as `sb` to every helper.
        """
        conn = self._pool.getconn()
        try:
            conn.autocommit = False
            tx = PostgresClient.__new__(PostgresClient)
            tx._pool = _TxPool(conn)
            tx.auth = self.auth
            try:
                yield tx
                if conn.get_transaction_status() == psycopg2.extensions.TRANSACTION_STATUS_INERROR:
                    # A statement failed and the caller swallowed the error. COMMIT would
                    # silently turn into ROLLBACK; fail loudly instead.
                    raise RuntimeError("transaction aborted by an earlier database error that was swallowed")
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        finally:
            conn.autocommit = True
            self._pool.putconn(conn)
```

In `QueryBuilder.execute` and `_RpcBuilder.execute`, replace `conn.autocommit = True` with:

```python
            if not getattr(self._pool, "in_tx", False):
                conn.autocommit = True
```

Update the type hints `_pool: ThreadedConnectionPool` only if a checker complains; behaviour is duck-typed.

- [ ] **Step 4: run, expect PASS** — same command.
- [ ] **Step 5: commit** — `feat(platform): add PostgresClient.transaction()`

---

### Task 3: F-039 — unknown nested relation raises

**Files:** `api/platform/postgres.py:198-201` (`_parse_select`), `tests/platform/test_select_parsing.py`

- [ ] **Step 1: failing test**

```python
import pytest


def test_unknown_nested_relation_raises(sb_client):
    with pytest.raises(ValueError, match="unpaid_invoices.*members"):
        sb_client.table("unpaid_invoices").select("*, members(name)")


def test_known_nested_relation_still_works(sb_client, member_id):
    row = sb_client.table("members").select("id, chapters(name)").eq("id", member_id).single().execute().data
    assert row["chapters"]["name"]
```

- [ ] **Step 2: run, expect the first test to FAIL** (no exception raised today).
- [ ] **Step 3: implement** — replace the `continue` under `if tbl not in fk_info:` with:

```python
                raise ValueError(
                    f'platform.postgres: "{self._table}" has no registered join to "{tbl}". '
                    "Add it to FK_MAP or read the related rows with a second query."
                )
```

- [ ] **Step 4: check callers.** Run `grep -rnP '\.select\(\s*f?"[^"]*\w+\(' api`. Every hit must use a relation registered in `FK_MAP` for its base table. On 2026-10-05 the hits were `api/dependencies.py:22`, `api/attendance/api/excuses.py:90,99`, `api/attendance/services/checkin_links.py:236,292`, all registered. If a new one is not, report it; do not edit other domains.
- [ ] **Step 5: run, expect PASS; commit** — `fix(platform): fail fast on unregistered nested selects`

---

### Task 4: R-04 — validate identifiers

Column names, order columns, payload keys, `on_conflict` and select tokens are interpolated into SQL. No request-controlled value reaches them today; this makes that structural.

**Files:** `api/platform/postgres.py`, `tests/platform/test_identifiers.py`

- [ ] **Step 1: failing tests**

```python
import pytest

BAD = 'id"; DROP TABLE members; --'


@pytest.mark.parametrize("build", [
    lambda sb: sb.table("members").select("*").eq(BAD, 1).execute(),
    lambda sb: sb.table("members").select("*").in_(BAD, [1]).execute(),
    lambda sb: sb.table("members").select("*").order(BAD).execute(),
    lambda sb: sb.table("members").select(f"id, {BAD}").execute(),
    lambda sb: sb.table("members").insert({BAD: 1}).execute(),
    lambda sb: sb.table("members").update({BAD: 1}).eq("id", "x").execute(),
    lambda sb: sb.table("members").upsert({"id": "x"}, on_conflict=BAD).execute(),
    lambda sb: sb.table(BAD).select("*").execute(),
])
def test_bad_identifier_rejected(sb_client, build):
    with pytest.raises(ValueError, match="identifier"):
        build(sb_client)


def test_dotted_join_filter_allowed(sb_client, chapter_id):
    sb_client.table("attendance").select("id, events(title)").eq("events.chapter_id", chapter_id).execute()
```

- [ ] **Step 2: run, expect FAIL** (psycopg2 errors or no error, not `ValueError`).
- [ ] **Step 3: implement**

```python
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT.fullmatch(name):
        raise ValueError(f"platform.postgres: invalid identifier {name!r}")
    return name
```

Call it: on the table name in `PostgresClient.table`; on each select token in `_parse_select` (skip `*`) and each join table and join column; on filter columns in `_build_where` (for a dotted name, validate both halves); on `_order_col` in `_exec_select`; on payload keys in `_exec_insert`, `_exec_update`, `_exec_upsert`; on each comma-separated part of `on_conflict` (strip spaces). Reuse `_IDENT` in `_RpcBuilder.execute` in place of the two inline regexes.

- [ ] **Step 4: run, expect PASS; commit** — `fix(platform): validate SQL identifiers in the query builder`

---

### Task 5: R-03 — keep `Decimal` as `Decimal`

**Files:** `api/platform/postgres.py:436-455` (`_serialize`), `tests/platform/test_serialize.py`

- [ ] **Step 1: failing test**

```python
from decimal import Decimal
from api.platform.postgres import QueryBuilder


def test_serialize_keeps_decimal():
    out = QueryBuilder._serialize({"amount": Decimal("12.10")})
    assert out["amount"] == Decimal("12.10") and isinstance(out["amount"], Decimal)
```

- [ ] **Step 2: run, expect FAIL** (`float`).
- [ ] **Step 3: implement** — delete the `elif isinstance(v, Decimal): out[k] = float(v)` branch and the now-unused `Decimal` import. Fix the docstring: "Convert UUID and date/time values to strings."
- [ ] **Step 4: run** `python3 -m pytest tests/platform tests/events tests/treasury -q -x`. If a test fails on `Decimal is not JSON serializable`, fix the call site that dumps the row (convert with `Money.from_numeric(...).cents` when it is money, `str(...)` otherwise) and add that file to your report. Never restore the float conversion.
- [ ] **Step 5: commit** — `fix(platform): stop converting Decimal to float in RETURNING rows`

---

### Task 6: F-021 — the outbox enqueue stops swallowing every error

`enqueue` and `enqueue_many` (`api/platform/outbox.py:60-177`) catch `Exception` on insert and report "already queued". A missing column, a dropped connection or a constraint error looks identical to a duplicate, and the notification is silently lost. Inside a transaction the try/except pattern would also abort the transaction.

**Files:** `api/platform/postgres.py`, `api/platform/outbox.py`, `api/treasury/notifications.py:1-25` (docstring), `tests/platform/test_outbox_enqueue.py`

**Interfaces (produced):**

```python
sb.table("message_outbox").insert(row_or_rows, ignore_conflict="dedup_key").execute()
# INSERT … ON CONFLICT (dedup_key) DO NOTHING RETURNING *  → .data holds only the rows actually inserted
```

`enqueue(...)` keeps its signature and return (`dict | None`); `enqueue_many(...)` keeps returning the number of rows queued.

- [ ] **Step 1: failing tests** (`chapter_id`, `member_factory`, `sb_client`):
  - `test_insert_ignore_conflict_returns_only_new_rows`: insert a `message_outbox` row with dedup key K through `enqueue`; then `sb_client.table("message_outbox").insert([rowK, rowK2], ignore_conflict="dedup_key").execute().data` has exactly one row (K2). Build rows with the module's `_row(...)` helper.
  - `test_enqueue_duplicate_returns_none_without_error`: second `enqueue` with the same key returns `None`.
  - `test_enqueue_real_failure_is_not_reported_as_duplicate`: call `enqueue` with a `chapter_id` that does not exist (foreign-key violation). Outside a transaction: returns `None` AND an error is logged (`caplog` has a record at ERROR from `api.platform.outbox`). Inside `with sb_client.transaction() as tx:` with `sb=tx`: the exception propagates.
  - `test_enqueue_duplicate_inside_transaction_does_not_abort_it`: inside a transaction, enqueue key K twice, then insert a chapter; the block commits and the chapter exists.
  - `test_enqueue_many_counts_only_new_rows`.
- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement.**
  - `postgres.py`: `QueryBuilder` gets a field `_ignore_conflict: str | None = None`; `_TableAccessor.insert(self, data, *, ignore_conflict: str | None = None)` passes it; `_exec_insert` appends `ON CONFLICT (<validated, comma-separated identifiers>) DO NOTHING` before `RETURNING *` when it is set (validate each part with `_ident`).
  - `outbox.py`, `enqueue`: delete the pre-select and the try/except. One call: `result = client.table("message_outbox").insert(row, ignore_conflict="dedup_key").execute()`; return the row, or `None` when `.data` is empty. Wrap that call: `except Exception: if getattr(getattr(client, "_pool", None), "in_tx", False): raise` else `logger.exception("outbox enqueue failed for %s", dedup_key); return None`.
  - `enqueue_many`: delete the pre-select and the per-row fallback. One bulk insert with `ignore_conflict="dedup_key"`; return `len(result.data)`; same error rule as `enqueue`.
  - `api/treasury/notifications.py:1-25`: the docstring claims the enqueue is transactional. Rewrite it to say what is true: the enqueue runs after the money RPC commits; it is idempotent on `dedup_key`; a failure is logged, not raised, unless the caller passed a transaction client.
- [ ] **Step 4: run `python3 -m pytest tests/platform tests/cron tests/announcements tests/auth tests/treasury -q`.** Fix tests that pinned the old behaviour (list them in the report). **Commit** — `fix(platform): outbox enqueue uses ON CONFLICT and stops hiding real failures`

---

### Task 7: full suite

- [ ] Run `python3 -m pytest -q` from `LocalDev/` (about 11 minutes). Expected: the 1030 baseline tests plus yours pass. Report the final count line verbatim. A failure caused by Tasks 3, 4 or 6 rejecting a legitimate query is fixed by widening the validator deliberately (say what and why), not by removing the check.
