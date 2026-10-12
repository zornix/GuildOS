#!/usr/bin/env python3
"""Rebuild the demo database: drop everything in public, replay every
migration, seed Delta Mu. Demo/local databases only.

  npm run reset-demo                  # asks you to type the project ref
  npm run reset-demo -- --dry-run     # does all of it, then rolls back

It all runs in one transaction, so a failing migration or seed leaves the
database as it was. It locks every table while it runs: stop tests, agents
and the local backend first.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_guard import ProdGuardError, project_ref, redact, require_demo
from scripts.migrate_db import (
    MIGRATIONS_DIR,
    _database_url,
    _ensure_migrations_table,
    _read_sql,
    duplicate_numbers,
)
from scripts.seed import seed_rows

# Everything the migrations create lives in public. The schema itself and
# extension-owned objects stay, so Supabase's grants survive and
# CREATE EXTENSION IF NOT EXISTS stays a no-op on replay.
DROP_PUBLIC = """
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                              WHEN 'S' THEN 'SEQUENCE' WHEN 'f' THEN 'FOREIGN TABLE'
                              ELSE 'TABLE' END AS kind,
               format('%I.%I', n.nspname, c.relname) AS name
          FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
           AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = c.oid AND d.deptype = 'e')
    LOOP
        EXECUTE format('DROP %s IF EXISTS %s CASCADE', r.kind, r.name);
    END LOOP;

    FOR r IN
        SELECT p.oid::regprocedure::text AS name
          FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = p.oid AND d.deptype = 'e')
    LOOP
        EXECUTE format('DROP ROUTINE IF EXISTS %s CASCADE', r.name);
    END LOOP;

    FOR r IN
        SELECT CASE t.typtype WHEN 'd' THEN 'DOMAIN' ELSE 'TYPE' END AS kind,
               format('%I.%I', n.nspname, t.typname) AS name
          FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
         WHERE n.nspname = 'public' AND t.typtype IN ('e', 'd', 'r', 'm', 'c')
           AND (t.typtype <> 'c' OR (SELECT relkind FROM pg_class WHERE oid = t.typrelid) = 'c')
           AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid = t.oid AND d.deptype = 'e')
    LOOP
        EXECUTE format('DROP %s IF EXISTS %s CASCADE', r.kind, r.name);
    END LOOP;
END $$;
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Drop, migrate and seed the demo database.")
    parser.add_argument("--yes", action="store_true", help="skip the typed confirmation")
    parser.add_argument("--dry-run", action="store_true", help="do everything, then roll back")
    args = parser.parse_args(argv)

    url = _database_url()
    try:
        require_demo(url, context="reset-demo")
    except ProdGuardError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    dupes = duplicate_numbers([f.name for f in files])
    if dupes:
        print(f"error: these migrations share a number: {', '.join(dupes)}", file=sys.stderr)
        return 1

    if not (args.yes or args.dry_run):
        expected = project_ref(url) or "local"
        print(f"This wipes every table in {redact(url)} and rebuilds it.")
        try:
            typed = input(f"Type {expected} to continue: ")
        except EOFError:
            typed = ""
        if typed.strip() != expected:
            print("error: confirmation mismatch — nothing changed", file=sys.stderr)
            return 1

    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = 0")
            cur.execute(DROP_PUBLIC)
            print("dropped: everything in public")
            _ensure_migrations_table(cur)
            for path in files:
                sql = _read_sql(path)
                if not sql:
                    continue  # migrate_db.py skips empty files without recording them
                try:
                    cur.execute(sql)
                except Exception:
                    print(f"failed: {path.name}", file=sys.stderr)
                    raise
                cur.execute(
                    "INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)",
                    (path.name, hashlib.sha256(path.read_bytes()).hexdigest()),
                )
            print(f"applied: {len(files)} migrations")
            seed_rows(cur)
            print("seeded: Delta Mu")
        if args.dry_run:
            conn.rollback()
            print("dry run: rolled back, nothing changed")
        else:
            conn.commit()
            print(f"reset done: {redact(url)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
