#!/usr/bin/env python3
"""Report old test-chapter rows; --apply deletes them only on demo/local DBs."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import psycopg2
from psycopg2 import sql

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.db_guard import require_demo
from scripts.migrate_db import _database_url

# Audited INSERTs and API-created names in tests/{treasury,recruitment,
# attendance,announcements,platform,events,rbac,contribution,chapters}.
TEST_PREFIXES = ('tr-test-', 'rc-test-', 'at-test-', 'ob-test-', 'tx-test-',
                 'tx-outbox-', 'foreign-', 'other-', 'rbac-other-', 'contrib-other-')
# Fixed tenant-guard names must not become broad "other" prefixes.
TEST_NAMES = frozenset({'other', 'other2', 'ev-other', 'in-other', 'other-get',
                        'other-jobs', 'Other delete chapter'})
DELETE_GUARD_TABLES = ('big_ledger', 'audit_logs', 'receipts', 'payment_allocations',
                       'payment_evidence', 'invoice_line_items',
                       'announcement_sms_sends', 'event_notification_sends',
                       'security_swap_requests', 'task_commitment_log',
                       'finance_adjustments', 'refunds', 'fines', 'usage_events')
# These legacy FKs do not cascade. Delete their scoped rows before chapters.
LEGACY_DELETE_ORDER = ('receipts', 'initiative_chairs', 'initiatives',
                       'attendance', 'checkin_links', 'excuses')


def is_test_chapter(name: str) -> bool:
    return (name.startswith(TEST_PREFIXES) or name in TEST_NAMES
            or re.fullmatch(r'Chapter [0-9a-f]{12}', name) is not None)


def row_counts(cur, tables, chapter_ids):
    counts = {}
    for table in ['chapters', *tables]:
        column = 'id' if table == 'chapters' else 'chapter_id'
        cur.execute(sql.SQL('SELECT count(*) FROM public.{} WHERE {} = ANY(%s::uuid[])')
                    .format(sql.Identifier(table), sql.Identifier(column)), (chapter_ids,))
        counts[table] = cur.fetchone()[0]
    return counts


def print_counts(label, counts):
    for table, count in counts.items():
        print(f'{label}: {table}={count}')


def apply_purge(cur, chapter_ids):
    """The caller owns one transaction; the savepoint also restores DDL on error."""
    cur.execute('SAVEPOINT purge_test_chapters')
    try:
        cur.execute("""
            SELECT c.relname, t.tgname, t.tgenabled
            FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)
              AND NOT t.tgisinternal AND (t.tgtype::int & 8) <> 0
              AND t.tgenabled <> 'D'
            ORDER BY c.relname, t.tgname
        """, (list(DELETE_GUARD_TABLES),))
        triggers = cur.fetchall()
        for table, trigger, _ in triggers:
            cur.execute(sql.SQL('ALTER TABLE public.{} DISABLE TRIGGER {}')
                        .format(sql.Identifier(table), sql.Identifier(trigger)))
        for table in LEGACY_DELETE_ORDER:
            cur.execute(sql.SQL('DELETE FROM public.{} WHERE chapter_id = ANY(%s::uuid[])')
                        .format(sql.Identifier(table)), (chapter_ids,))
        cur.execute('DELETE FROM public.chapters WHERE id = ANY(%s::uuid[])', (chapter_ids,))
        for table, trigger, state in triggers:
            mode = {'O': 'ENABLE', 'R': 'ENABLE REPLICA', 'A': 'ENABLE ALWAYS'}[state]
            cur.execute(sql.SQL('ALTER TABLE public.{} {} TRIGGER {}')
                        .format(sql.Identifier(table), sql.SQL(mode), sql.Identifier(trigger)))
    except BaseException:
        # PostgreSQL rolls back every DISABLE TRIGGER, including failures while
        # restoring triggers. No re-enable query is issued in an aborted txn.
        cur.execute('ROLLBACK TO SAVEPOINT purge_test_chapters')
        raise
    finally:
        cur.execute('RELEASE SAVEPOINT purge_test_chapters')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--older-than-days', type=int, default=2)
    parser.add_argument('--apply', action='store_true', help='delete instead of reporting')
    parser.add_argument('--batch-size', type=int, default=500,
                        help='chapters deleted per transaction (one big delete hits the pooler timeout)')
    args = parser.parse_args(argv)
    if args.older_than_days < 0:
        parser.error('--older-than-days must be nonnegative')
    if args.batch_size < 1:
        parser.error('--batch-size must be positive')
    url = _database_url()
    require_demo(url, context='purge_test_chapters')  # Before any connection.
    conn = psycopg2.connect(url)
    try:
        conn.set_session(readonly=not args.apply, isolation_level='REPEATABLE READ')
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id::text, name FROM public.chapters "
                            "WHERE created_at < now() - (%s * interval '1 day') "
                            "AND (name LIKE ANY(%s) OR name = ANY(%s) "
                            "OR name ~ '^Chapter [0-9a-f]{12}$') "
                            "ORDER BY id" + (' FOR UPDATE' if args.apply else ''),
                            (args.older_than_days, [prefix + '%' for prefix in TEST_PREFIXES],
                             sorted(TEST_NAMES)))
                ids = [cid for cid, name in cur.fetchall() if is_test_chapter(name)]
                cur.execute("SELECT table_name FROM information_schema.columns "
                            "WHERE table_schema='public' AND column_name='chapter_id' "
                            "ORDER BY table_name")
                tables = [row[0] for row in cur.fetchall()]
                print_counts('BEFORE' if args.apply else 'DRY RUN', row_counts(cur, tables, ids))
        # ponytail: each batch commits on its own, so a failure leaves earlier batches purged;
        # rerunning picks up the rest. One transaction for all of them hit statement_timeout.
        for start in range(0, len(ids) if args.apply else 0, args.batch_size):
            with conn, conn.cursor() as cur:
                cur.execute('SET LOCAL statement_timeout = 0')
                apply_purge(cur, ids[start:start + args.batch_size])
            print(f'deleted {min(start + args.batch_size, len(ids))}/{len(ids)} chapters', flush=True)
        if args.apply:
            with conn, conn.cursor() as cur:
                print_counts('AFTER', row_counts(cur, tables, ids))
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Driver errors can contain connection details or row contents: name the class only,
        # except for the guard, whose message is already safe to show.
        detail = str(exc) if type(exc).__name__ == 'ProdGuardError' else type(exc).__name__
        print(f'Purge failed ({detail}); no changes committed.', file=sys.stderr)
        raise SystemExit(1)
