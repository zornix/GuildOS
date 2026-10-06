"""
The database client: a query builder backed by psycopg2.

Per ADR-0002 this is *the* client in every environment — demo and prod are both
Supabase-hosted Postgres reached over the pooler by `DATABASE_URL`, and
supabase-py is not installed. The builder surface below is PostgREST-shaped for
historical reasons; it is no longer a "local fallback" for anything.

Supported calls:
  sb.table("x").select("cols").eq("c", v).execute()
  sb.table("x").insert({...}).execute()
  sb.table("x").update({...}).eq(...).execute()
  sb.table("x").delete().eq(...).execute()
  sb.table("x").upsert({...}, on_conflict="a,b").execute()

Join syntax ("*, related(col1, col2)") is translated to LEFT JOINs
with results nested under the relation key, matching PostgREST output.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

FK_MAP: dict[str, dict[str, tuple[str, str]]] = {
    "members":       {"chapters": ("chapter_id", "id")},
    "events":        {"chapters": ("chapter_id", "id"), "members": ("created_by", "id")},
    "attendance":    {"events": ("event_id", "id"), "members": ("member_id", "id")},
    "excuses":       {"events": ("event_id", "id"), "members": ("member_id", "id")},
    "fines":         {"events": ("event_id", "id"), "members": ("member_id", "id"), "chapters": ("chapter_id", "id")},
    "checkin_links": {"events": ("event_id", "id"), "members": ("created_by", "id")},
}

# For join clauses like chapters(*) / events(*) — expand to aliased columns so joined
# "id", "name", etc. do not overwrite the base row (RealDictCursor keeps one key per name).
JOIN_STAR_COLUMNS: dict[str, list[str]] = {
    "chapters": ["id", "name", "organization", "school", "created_at"],
    "events": [
        "id",
        "chapter_id",
        "title",
        "description",
        "date",
        "time",
        "location",
        "required",
        "fine_amount",
        "created_by",
        "created_at",
    ],
    "members": ["id", "chapter_id", "name", "email", "phone", "role", "status", "created_at"],
}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT.fullmatch(name):
        raise ValueError(f"platform.postgres: invalid identifier {name!r}")
    return name


class _TxPool:
    """Stands in for the pool inside a transaction: always the same connection."""

    in_tx = True

    def __init__(self, conn):
        self._conn = conn

    def getconn(self):
        if self._conn is None:
            raise RuntimeError("platform.postgres: this transaction client was used after its block ended")
        return self._conn

    def putconn(self, conn):
        pass

    def release(self):
        """Called when the block ends: the connection goes back to the pool, so a
        leaked `tx` must fail instead of writing into another request's transaction."""
        self._conn = None


@dataclass
class QueryResult:
    data: list[dict] | dict | None
    count: int | None = None


@dataclass
class _Join:
    table: str
    cols: list[str] | None  # None = all columns
    fk_local: str
    fk_remote: str


@dataclass
class QueryBuilder:
    _pool: ThreadedConnectionPool
    _table: str
    _op: str = "select"
    _select_cols: str = "*"
    _count_mode: str | None = None
    _joins: list[_Join] = field(default_factory=list)
    _filters: list[tuple[str, str, Any]] = field(default_factory=list)
    _order_col: str | None = None
    _order_desc: bool = False
    _is_single: bool = False
    _payload: dict | None = None
    _on_conflict: str | None = None
    _ignore_conflict: str | bool | None = None
    _chain_select: str | None = None
    _limit_n: int | None = None
    _offset_n: int | None = None

    # ── builder methods ──────────────────────────────────────────

    def select(self, cols: str = "*", *, count: str | None = None) -> QueryBuilder:
        if self._op in ("update", "delete"):
            self._chain_select = cols
            return self
        self._op = "select"
        self._count_mode = count
        self._parse_select(cols)
        return self

    def insert(self, data: dict | list[dict]) -> QueryBuilder:
        self._op = "insert"
        self._payload = data
        return self

    def update(self, data: dict) -> QueryBuilder:
        self._op = "update"
        self._payload = data
        return self

    def delete(self) -> QueryBuilder:
        self._op = "delete"
        return self

    def upsert(self, data: dict, *, on_conflict: str | None = None) -> QueryBuilder:
        self._op = "upsert"
        self._payload = data
        self._on_conflict = on_conflict
        return self

    def eq(self, col: str, val: Any) -> QueryBuilder:
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col: str, vals: list) -> QueryBuilder:
        self._filters.append(("in", col, vals))
        return self

    def not_in_(self, col: str, vals: list) -> QueryBuilder:
        self._filters.append(("not_in", col, vals))
        return self

    def lte(self, col: str, val: Any) -> QueryBuilder:
        self._filters.append(("lte", col, val))
        return self

    def gte(self, col: str, val: Any) -> QueryBuilder:
        self._filters.append(("gte", col, val))
        return self

    def order(self, col: str, *, desc: bool = False) -> QueryBuilder:
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int) -> QueryBuilder:
        self._limit_n = n
        return self

    def range(self, start: int, end: int) -> QueryBuilder:
        # PostgREST-style inclusive range: rows [start, end].
        self._offset_n = start
        self._limit_n = end - start + 1
        return self

    def single(self) -> QueryBuilder:
        self._is_single = True
        return self

    def maybe_single(self) -> QueryBuilder:
        """Like single() but returns None instead of raising when no rows found."""
        self._is_single = True
        return self

    # ── execution ────────────────────────────────────────────────

    def execute(self) -> QueryResult:
        conn = self._pool.getconn()
        try:
            if not getattr(self._pool, "in_tx", False):
                conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if self._op == "select":
                    return self._exec_select(cur)
                elif self._op == "insert":
                    return self._exec_insert(cur)
                elif self._op == "update":
                    return self._exec_update(cur)
                elif self._op == "delete":
                    return self._exec_delete(cur)
                elif self._op == "upsert":
                    return self._exec_upsert(cur)
                raise ValueError(f"Unknown op: {self._op}")
        finally:
            self._pool.putconn(conn)

    # ── select ───────────────────────────────────────────────────

    def _parse_select(self, raw: str):
        join_pattern = re.compile(r"(\w+)\(([^)]*)\)")
        joins_found = join_pattern.findall(raw)
        remainder = join_pattern.sub("", raw)
        tokens = [p.strip() for p in remainder.split(",") if p.strip()]
        for tok in tokens:
            if tok != "*":
                _ident(tok)
        # After stripping join clauses, commas often leave "", which must not become empty SELECT columns.
        self._select_cols = "*" if not tokens or tokens == ["*"] else ",".join(tokens)

        fk_info = FK_MAP.get(self._table, {})
        for tbl, cols_str in joins_found:
            _ident(tbl)
            if tbl not in fk_info:
                raise ValueError(
                    f'platform.postgres: "{self._table}" has no registered join to "{tbl}". '
                    "Add it to FK_MAP or read the related rows with a second query."
                )
            fk_local, fk_remote = fk_info[tbl]
            raw = cols_str.strip()
            if raw == "*":
                cols = JOIN_STAR_COLUMNS.get(tbl)
                if not cols:
                    raise ValueError(
                        f'platform.postgres: join "{tbl}(*)" needs a JOIN_STAR_COLUMNS entry '
                        "or use explicit columns, e.g. chapters(name)."
                    )
            else:
                cols = [_ident(c.strip()) for c in cols_str.split(",") if c.strip()]
                if not cols:
                    raise ValueError(f'platform.postgres: "{tbl}()" names no columns; use {tbl}(*) or list them.')
            self._joins.append(_Join(table=tbl, cols=cols, fk_local=fk_local, fk_remote=fk_remote))

    def _exec_select(self, cur) -> QueryResult:
        t = self._table
        alias = t[0]

        if self._select_cols == "*":
            select_parts = [f'"{t}".*']
        else:
            select_parts = [f'"{t}".{c.strip()}' for c in self._select_cols.split(",") if c.strip()]

        join_clauses: list[str] = []
        join_col_map: dict[str, list[str]] = {}

        for j in self._joins:
            ja = f"_j_{j.table}"
            if j.cols:
                for c in j.cols:
                    select_parts.append(f'"{ja}".{c} AS "_j_{j.table}__{c}"')
                join_col_map[j.table] = j.cols
            else:
                select_parts.append(f'"{ja}".*')
                join_col_map[j.table] = None
            join_clauses.append(
                f'LEFT JOIN "{j.table}" "{ja}" ON "{t}"."{j.fk_local}" = "{ja}"."{j.fk_remote}"'
            )

        where_parts, params = self._build_where(t)

        sql = f'SELECT {", ".join(select_parts)} FROM "{t}" {" ".join(join_clauses)}'
        if where_parts:
            sql += f" WHERE {' AND '.join(where_parts)}"
        if self._order_col:
            direction = "DESC" if self._order_desc else "ASC"
            sql += f' ORDER BY "{t}"."{_ident(self._order_col)}" {direction}'

        # LIMIT/OFFSET as validated integer literals (count query intentionally omits them).
        if self._limit_n is not None:
            sql += f" LIMIT {int(self._limit_n)}"
        if self._offset_n is not None:
            sql += f" OFFSET {int(self._offset_n)}"

        if self._count_mode == "exact":
            count_sql = f'SELECT COUNT(*) FROM "{t}" {" ".join(join_clauses)}'
            if where_parts:
                count_sql += f" WHERE {' AND '.join(where_parts)}"
            cur.execute(count_sql, params)
            count_val = cur.fetchone()["count"]
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            rows = self._nest_joins(rows, join_col_map)
            data = rows[0] if self._is_single and rows else rows
            return QueryResult(data=data, count=count_val)

        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        rows = self._nest_joins(rows, join_col_map)

        if self._is_single:
            return QueryResult(data=rows[0] if rows else None)
        return QueryResult(data=rows)

    def _nest_joins(self, rows: list[dict], join_col_map: dict[str, list[str] | None]) -> list[dict]:
        if not join_col_map:
            return rows

        result = []
        for row in rows:
            new_row = {}
            nested: dict[str, dict] = {tbl: {} for tbl in join_col_map}

            for k, v in row.items():
                placed = False
                for tbl in join_col_map:
                    prefix = f"_j_{tbl}__"
                    if k.startswith(prefix):
                        col_name = k[len(prefix):]
                        nested[tbl][col_name] = v
                        placed = True
                        break
                if not placed:
                    new_row[k] = v

            for tbl, cols in join_col_map.items():
                if cols is not None:
                    new_row[tbl] = nested[tbl] if any(v is not None for v in nested[tbl].values()) else None
                else:
                    join_data = {}
                    for k, v in row.items():
                        if k.startswith(f"_j_{tbl}__"):
                            join_data[k[len(f"_j_{tbl}__"):]] = v
                    new_row[tbl] = (
                        join_data
                        if join_data and any(v is not None for v in join_data.values())
                        else None
                    )

            result.append(new_row)
        return result

    # ── insert ───────────────────────────────────────────────────

    def _exec_insert(self, cur) -> QueryResult:
        # A list payload is one multi-row INSERT — every row must carry the same
        # columns (PostgREST behaves the same way).
        rows = self._payload if isinstance(self._payload, list) else [self._payload]
        if not rows:
            return QueryResult(data=[])
        cols = [_ident(c) for c in rows[0].keys()]
        row_sql = "(" + ", ".join(["%s"] * len(cols)) + ")"
        vals = [self._adapt_value(r[c]) for r in rows for c in cols]
        col_str = ", ".join(f'"{c}"' for c in cols)
        sql = f'INSERT INTO "{self._table}" ({col_str}) VALUES {", ".join([row_sql] * len(rows))}'
        if self._ignore_conflict is True:
            sql += " ON CONFLICT DO NOTHING"
        elif self._ignore_conflict:
            # Rows that hit the conflict are skipped and absent from RETURNING.
            conflict = ", ".join(_ident(c.strip()) for c in self._ignore_conflict.split(","))
            sql += f" ON CONFLICT ({conflict}) DO NOTHING"
        sql += " RETURNING *"
        cur.execute(sql, vals)
        return QueryResult(data=[self._serialize(dict(r)) for r in cur.fetchall()])

    # ── update ───────────────────────────────────────────────────

    def _exec_update(self, cur) -> QueryResult:
        set_parts = []
        vals = []
        for k, v in self._payload.items():
            set_parts.append(f'"{_ident(k)}" = %s')
            vals.append(self._adapt_value(v))

        where_parts, where_vals = self._build_where(self._table)
        vals.extend(where_vals)

        returning = " RETURNING *"
        sql = f'UPDATE "{self._table}" SET {", ".join(set_parts)}'
        if where_parts:
            sql += f" WHERE {' AND '.join(where_parts)}"
        sql += returning
        cur.execute(sql, vals)
        rows = [self._serialize(dict(r)) for r in cur.fetchall()]
        if self._is_single:
            return QueryResult(data=rows[0] if rows else None)
        return QueryResult(data=rows)

    # ── delete ───────────────────────────────────────────────────

    def _exec_delete(self, cur) -> QueryResult:
        where_parts, params = self._build_where(self._table)
        sql = f'DELETE FROM "{self._table}"'
        if where_parts:
            sql += f" WHERE {' AND '.join(where_parts)}"
        cur.execute(sql, params)
        return QueryResult(data=[])

    # ── upsert ───────────────────────────────────────────────────

    def _exec_upsert(self, cur) -> QueryResult:
        cols = [_ident(c) for c in self._payload.keys()]
        placeholders = ["%s"] * len(cols)
        vals = [self._adapt_value(self._payload[c]) for c in cols]
        col_str = ", ".join(f'"{c}"' for c in cols)

        conflict = [_ident(c.strip()) for c in (self._on_conflict or "id").split(",")]
        conflict_cols = ", ".join(conflict)
        update_cols = [c for c in cols if c not in conflict]
        update_str = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_cols)

        sql = (
            f'INSERT INTO "{self._table}" ({col_str}) VALUES ({", ".join(placeholders)}) '
            f'ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_str} '
            f'RETURNING *'
        )
        cur.execute(sql, vals)
        row = dict(cur.fetchone())
        return QueryResult(data=[self._serialize(row)])

    # ── helpers ──────────────────────────────────────────────────

    def _build_where(self, table: str) -> tuple[list[str], list]:
        parts = []
        params = []
        for op, col, val in self._filters:
            if "." in col:
                tbl, c = col.split(".", 1)
                qualified = f'"_j_{_ident(tbl)}"."{_ident(c)}"'
            else:
                qualified = f'"{table}"."{_ident(col)}"'

            if op == "eq":
                parts.append(f"{qualified} = %s")
                params.append(self._adapt_value(val))
            elif op == "in":
                if not val:
                    parts.append("FALSE")
                else:
                    # IN (%s,...) avoids ANY(text[]) vs uuid[] mismatches (e.g. event_id filters).
                    ph = ", ".join(["%s"] * len(val))
                    parts.append(f"{qualified} IN ({ph})")
                    params.extend(self._adapt_value(v) for v in val)
            elif op == "not_in":
                if val:
                    ph = ", ".join(["%s"] * len(val))
                    parts.append(f"{qualified} NOT IN ({ph})")
                    params.extend(self._adapt_value(v) for v in val)
            elif op == "lte":
                if val == "now()":
                    parts.append(f"{qualified} <= NOW()")
                else:
                    parts.append(f"{qualified} <= %s")
                    params.append(self._adapt_value(val))
            elif op == "gte":
                if val == "now()":
                    parts.append(f"{qualified} >= NOW()")
                else:
                    parts.append(f"{qualified} >= %s")
                    params.append(self._adapt_value(val))
        return parts, params

    @staticmethod
    def _adapt_value(v: Any) -> Any:
        if isinstance(v, (dict, list)):
            return psycopg2.extras.Json(v)
        return v

    @staticmethod
    def _serialize(row: dict) -> dict:
        """Convert UUID and date/time values to strings."""
        import datetime
        from uuid import UUID

        out = {}
        for k, v in row.items():
            if isinstance(v, UUID):
                out[k] = str(v)
            elif isinstance(v, (datetime.date, datetime.time)):
                out[k] = v.isoformat()
            elif isinstance(v, datetime.datetime):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out


class _TableAccessor:
    def __init__(self, pool: ThreadedConnectionPool, table: str):
        self._pool = pool
        self._table = table

    def select(self, cols: str = "*", *, count: str | None = None) -> QueryBuilder:
        qb = QueryBuilder(_pool=self._pool, _table=self._table)
        return qb.select(cols, count=count)

    def insert(self, data: dict | list[dict], *, ignore_conflict: str | bool | None = None) -> QueryBuilder:
        return QueryBuilder(
            _pool=self._pool, _table=self._table, _op="insert", _payload=data,
            _ignore_conflict=ignore_conflict,
        )

    def update(self, data: dict) -> QueryBuilder:
        return QueryBuilder(_pool=self._pool, _table=self._table, _op="update", _payload=data)

    def delete(self) -> QueryBuilder:
        return QueryBuilder(_pool=self._pool, _table=self._table, _op="delete")

    def upsert(self, data: dict, *, on_conflict: str | None = None) -> QueryBuilder:
        return QueryBuilder(
            _pool=self._pool, _table=self._table,
            _op="upsert", _payload=data, _on_conflict=on_conflict,
        )



class _RpcBuilder:
    def __init__(self, pool: ThreadedConnectionPool, function_name: str, params: dict):
        self._pool = pool
        self._function_name = function_name
        self._params = params

    # RPC (function_name, param_name) pairs whose Postgres parameter is a true
    # SQL array type (e.g. `UUID[]`), not JSONB. Every other RPC's list/dict
    # params keep the original QueryBuilder._adapt_value JSON-encoding, which
    # is correct for JSONB-typed params such as ev_notify_event's
    # `p_recipient_member_ids JSONB` and ev_add_supervisor's
    # `p_required_role_keys JSONB` (see migrations/0143_event_notify.sql,
    # migrations/0141_events_v1_times_supervisors.sql).
    #
    # Scalar lists for these pairs are rendered as a raw Postgres array-literal
    # STRING (e.g. '{"a","b"}') rather than handed to psycopg2's native list
    # adapter: psycopg2's adapter emits `ARRAY['a','b']`, which Postgres
    # resolves to an explicit `text[]` type immediately, and a PL/pgSQL
    # function call has no implicit cast from `text[]` to a differently typed
    # array parameter (e.g. `uuid[]`) -- it fails with "function ... does not
    # exist". A quoted array-literal string is untyped ("unknown") until the
    # function call resolves it, so Postgres implicitly casts it to whatever
    # the parameter declares.
    _ARRAY_TYPED_RPC_PARAMS = {
        ("in_create_initiative", "p_chair_member_ids"),
    }

    @classmethod
    def _adapt_rpc_param(cls, function_name: str, param_name: str, v):
        if (function_name, param_name) in cls._ARRAY_TYPED_RPC_PARAMS and isinstance(v, list):

            def _quote(item):
                s = str(item).replace("\\", "\\\\").replace('"', '\\"')
                return f'"{s}"'

            return "{" + ",".join(_quote(item) for item in v) + "}"
        return QueryBuilder._adapt_value(v)

    def execute(self) -> QueryResult:
        if not _IDENT.fullmatch(self._function_name):
            raise ValueError(f"Invalid RPC function name: {self._function_name!r}")
        for key in self._params:
            if not _IDENT.fullmatch(key):
                raise ValueError(f"Invalid RPC parameter name: {key!r}")

        arg_sql = ", ".join(f"{key} => %s" for key in self._params)
        sql = f'SELECT "{self._function_name}"({arg_sql}) AS result'
        vals = [
            self._adapt_rpc_param(self._function_name, key, v)
            for key, v in self._params.items()
        ]

        conn = self._pool.getconn()
        try:
            if not getattr(self._pool, "in_tx", False):
                conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, vals)
                row = cur.fetchone()
                return QueryResult(data=row["result"] if row else None)
        finally:
            self._pool.putconn(conn)


class _LocalAuth:
    """Minimal auth shim — JWT decode only, no Supabase dependency."""

    def __init__(self, secret: str):
        self._secret = secret

    def get_user(self, token: str):
        import jwt
        try:
            # aud/iss are verified, and sub/exp are required, so a token minted
            # for another audience or missing its subject is rejected here rather
            # than blowing up on a KeyError below. Tokens issued before auth
            # hardening (0148) carry no aud/iss and fail this decode by design —
            # their holders are forced to log in again.
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                audience="guildos",
                issuer="guildos",
                options={"require": ["exp", "sub", "aud", "iss"]},
            )
        except jwt.InvalidTokenError as exc:
            raise Exception(f"Invalid token: {exc}")

        @dataclass
        class _User:
            id: str
            # Raw claims, so callers can check the token_version epoch ("ver").
            claims: dict = field(default_factory=dict)

        @dataclass
        class _AuthResponse:
            user: _User

        return _AuthResponse(user=_User(id=payload["sub"], claims=payload))


class PostgresClient:
    """Drop-in replacement for supabase.Client using local PostgreSQL."""

    def __init__(self, dsn: str, jwt_secret: str = "local-dev-secret"):
        self._pool = ThreadedConnectionPool(1, 10, dsn)
        self.auth = _LocalAuth(jwt_secret)

    def table(self, name: str) -> _TableAccessor:
        return _TableAccessor(self._pool, _ident(name))

    def rpc(self, name: str, params: dict | None = None) -> _RpcBuilder:
        return _RpcBuilder(self._pool, name, params or {})

    @contextmanager
    def transaction(self):
        """One connection, one transaction. Commit on exit, roll back on any error.

        Yields a client bound to that connection; pass it as `sb` to every helper.
        A helper that calls get_db() itself writes outside the transaction. Never
        catch a database error inside the block and carry on: exit then raises.
        Called on a transaction client, it joins that transaction.
        """
        if getattr(self._pool, "in_tx", False):
            yield self
            return
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
            tx._pool.release()
            if not conn.closed:
                conn.autocommit = True
            self._pool.putconn(conn)

    def close(self) -> None:
        self._pool.closeall()

    def ping(self) -> None:
        """Verify pool connectivity with a trivial query (for health checks)."""
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            self._pool.putconn(conn)
