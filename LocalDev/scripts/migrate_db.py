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

import argparse
import os
import sys
from pathlib import Path

import psycopg2

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "migrations"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.db_guard import (
    ProdGuardError,
    confirmation_matches,
    redact,
    require_demo,
    require_prod,
)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("error: set DATABASE_URL (e.g. from .env)", file=sys.stderr)
        sys.exit(1)
    return url


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply pending SQL migrations.")
    parser.add_argument(
        "--prod",
        action="store_true",
        help="migrate the production database (reads PROD_DATABASE_URL only)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the interactive prod confirmation (CI)",
    )
    return parser.parse_args()


def _env_value(key: str) -> str:
    """Read a key from the process env, falling back to LocalDev/.env."""
    value = os.environ.get(key, "").strip()
    if value:
        return value
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith(f"{key}="):
                return line.partition("=")[2].strip().strip('"')
    return ""


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
    args = _parse_args()

    if args.prod:
        url = _env_value("PROD_DATABASE_URL")
        if not url:
            print(
                "error: set PROD_DATABASE_URL (env or LocalDev/.env) — "
                "it is read only by migrate:prod, never by dev/test",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            require_prod(url)
        except ProdGuardError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        url = _database_url()
        try:
            require_demo(url, context="migrate")
        except ProdGuardError as exc:
            print(f"error: {exc}", file=sys.stderr)
            sys.exit(1)

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

        if args.prod:
            print(f"target: {redact(url)} (PROD)")
            print(f"pending migrations ({len(pending)}):")
            for path in pending:
                print(f"  {path.name}")
            if not args.yes:
                try:
                    typed = input("Type the prod project ref to apply them: ")
                except EOFError:
                    print("error: no confirmation input — nothing applied", file=sys.stderr)
                    sys.exit(1)
                if not confirmation_matches(typed, url):
                    print("error: confirmation mismatch — nothing applied", file=sys.stderr)
                    sys.exit(1)

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