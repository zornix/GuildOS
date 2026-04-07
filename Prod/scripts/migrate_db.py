#!/usr/bin/env python3
"""
Apply pending SQL migrations from migrations/*.sql in lexical order.

Requires DATABASE_URL (e.g. postgresql://user:pass@host:port/dbname).

Usage:
  export DATABASE_URL=postgresql://...
  python scripts/migrate_db.py

Tracks applied files in schema_migrations.
Each migration file is executed as a whole to support Postgres DO $$ ... $$ blocks,
functions, triggers, and other procedural SQL.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("error: set DATABASE_URL (e.g. from .env)", file=sys.stderr)
        sys.exit(1)
    return url


def _read_sql(path: Path) -> str:
    sql = path.read_text(encoding="utf-8").strip()
    if not sql:
        return ""
    return sql


def _ensure_migrations_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


def _applied_names(cur) -> set[str]:
    cur.execute("SELECT name FROM schema_migrations")
    return {row[0] for row in cur.fetchall()}


def main() -> None:
    url = _database_url()

    if not MIGRATIONS_DIR.is_dir():
        print(f"error: migrations directory missing: {MIGRATIONS_DIR}", file=sys.stderr)
        sys.exit(1)

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("no migrations/*.sql files found", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(url)

    try:
        conn.autocommit = False

        with conn.cursor() as cur:
            _ensure_migrations_table(cur)
        conn.commit()

        with conn.cursor() as cur:
            applied = _applied_names(cur)

        pending = [f for f in files if f.name not in applied]
        if not pending:
            print("schema_migrations: already up to date")
            return

        for path in pending:
            sql = _read_sql(path)
            if not sql:
                print(f"skip empty migration: {path.name}")
                continue

            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (name) VALUES (%s)",
                        (path.name,),
                    )
                conn.commit()
                print(f"applied: {path.name}")
            except Exception:
                conn.rollback()
                print(f"failed: {path.name}", file=sys.stderr)
                raise

        print("done.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()