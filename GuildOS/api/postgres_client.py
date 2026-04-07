"""
Supabase-compatible query builder backed by psycopg2.

Implements the subset of the supabase-py API actually used by the routes:
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
    _chain_select: str | None = None

    # ── builder methods ──────────────────────────────────────────

    def select(self, cols: str = "*", *, count: str | None = None) -> QueryBuilder:
        if self._op in ("update", "delete"):
            self._chain_select = cols
            return self
        self._op = "select"
        self._count_mode = count
        self._parse_select(cols)
        return self

    def insert(self, data: dict) -> QueryBuilder:
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

    def single(self) -> QueryBuilder:
        self._is_single = True
        return self

    # ── execution ────────────────────────────────────────────────

    def execute(self) -> QueryResult:
        conn = self._pool.getconn()
        try:
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
        remainder = join_pattern.sub("", raw).strip().rstrip(",").strip()
        self._select_cols = remainder if remainder else "*"

        fk_info = FK_MAP.get(self._table, {})
        for tbl, cols_str in joins_found:
            if tbl not in fk_info:
                continue
            fk_local, fk_remote = fk_info[tbl]
            cols = None if cols_str.strip() == "*" else [c.strip() for c in cols_str.split(",") if c.strip()]
            self._joins.append(_Join(table=tbl, cols=cols, fk_local=fk_local, fk_remote=fk_remote))

    def _exec_select(self, cur) -> QueryResult:
        t = self._table
        alias = t[0]

        if self._select_cols == "*":
            select_parts = [f'"{t}".*']
        else:
            select_parts = [f'"{t}".{c.strip()}' for c in self._select_cols.split(",")]

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
            sql += f' ORDER BY "{t}"."{self._order_col}" {direction}'

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
                    tbl_prefix = f"_j_{tbl}"
                    leftover_keys = [k for k in row if not k.startswith("_j_")]
                    for k, v in row.items():
                        if k.startswith(f"_j_{tbl}__"):
                            join_data[k[len(f"_j_{tbl}__"):]] = v
                    if not join_data:
                        for k, v in new_row.items():
                            pass
                        new_row[tbl] = None
                    else:
                        new_row[tbl] = join_data if any(v is not None for v in join_data.values()) else None

            result.append(new_row)
        return result

    # ── insert ───────────────────────────────────────────────────

    def _exec_insert(self, cur) -> QueryResult:
        cols = list(self._payload.keys())
        placeholders = ["%s"] * len(cols)
        vals = [self._payload[c] for c in cols]
        col_str = ", ".join(f'"{c}"' for c in cols)
        sql = f'INSERT INTO "{self._table}" ({col_str}) VALUES ({", ".join(placeholders)}) RETURNING *'
        cur.execute(sql, vals)
        row = dict(cur.fetchone())
        return QueryResult(data=[self._serialize(row)])

    # ── update ───────────────────────────────────────────────────

    def _exec_update(self, cur) -> QueryResult:
        set_parts = []
        vals = []
        for k, v in self._payload.items():
            set_parts.append(f'"{k}" = %s')
            vals.append(v)

        where_parts, where_vals = self._build_where(self._table)
        vals.extend(where_vals)

        returning = " RETURNING *" if self._chain_select else " RETURNING *"
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
        cols = list(self._payload.keys())
        placeholders = ["%s"] * len(cols)
        vals = [self._payload[c] for c in cols]
        col_str = ", ".join(f'"{c}"' for c in cols)

        conflict_cols = self._on_conflict or "id"
        update_cols = [c for c in cols if c not in conflict_cols.split(",")]
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
                qualified = f'"_j_{tbl}"."{c}"'
            else:
                qualified = f'"{table}"."{col}"'

            if op == "eq":
                parts.append(f"{qualified} = %s")
                params.append(val)
            elif op == "in":
                if not val:
                    parts.append("FALSE")
                else:
                    parts.append(f"{qualified} = ANY(%s)")
                    params.append(val)
            elif op == "lte":
                if val == "now()":
                    parts.append(f"{qualified} <= NOW()")
                else:
                    parts.append(f"{qualified} <= %s")
                    params.append(val)
            elif op == "gte":
                if val == "now()":
                    parts.append(f"{qualified} >= NOW()")
                else:
                    parts.append(f"{qualified} >= %s")
                    params.append(val)
        return parts, params

    @staticmethod
    def _serialize(row: dict) -> dict:
        """Convert non-JSON-serializable types to strings."""
        import datetime
        from decimal import Decimal
        from uuid import UUID

        out = {}
        for k, v in row.items():
            if isinstance(v, UUID):
                out[k] = str(v)
            elif isinstance(v, Decimal):
                out[k] = float(v)
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

    def insert(self, data: dict) -> QueryBuilder:
        return QueryBuilder(_pool=self._pool, _table=self._table, _op="insert", _payload=data)

    def update(self, data: dict) -> QueryBuilder:
        return QueryBuilder(_pool=self._pool, _table=self._table, _op="update", _payload=data)

    def delete(self) -> QueryBuilder:
        return QueryBuilder(_pool=self._pool, _table=self._table, _op="delete")

    def upsert(self, data: dict, *, on_conflict: str | None = None) -> QueryBuilder:
        return QueryBuilder(
            _pool=self._pool, _table=self._table,
            _op="upsert", _payload=data, _on_conflict=on_conflict,
        )


class _LocalAuth:
    """Minimal auth shim — JWT decode only, no Supabase dependency."""

    def __init__(self, secret: str):
        self._secret = secret
        self.admin = _LocalAuthAdmin()

    def get_user(self, token: str):
        import jwt
        try:
            payload = jwt.decode(token, self._secret, algorithms=["HS256"])
        except jwt.InvalidTokenError as exc:
            raise Exception(f"Invalid token: {exc}")

        @dataclass
        class _User:
            id: str

        @dataclass
        class _AuthResponse:
            user: _User

        return _AuthResponse(user=_User(id=payload["sub"]))


class _LocalAuthAdmin:
    def invite_user_by_email(self, email: str):
        pass


class PostgresClient:
    """Drop-in replacement for supabase.Client using local PostgreSQL."""

    def __init__(self, dsn: str, jwt_secret: str = "local-dev-secret"):
        self._pool = ThreadedConnectionPool(1, 10, dsn)
        self.auth = _LocalAuth(jwt_secret)

    def table(self, name: str) -> _TableAccessor:
        return _TableAccessor(self._pool, name)
