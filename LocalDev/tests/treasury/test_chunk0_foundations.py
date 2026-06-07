"""Chunk 0 — Foundations & Contracts (Treasury V1, Slice 0).

Test list is implemented verbatim from treasury-v1-implementation-plan.md §6 Slice 0:
  - Money rejects float construction; arithmetic is exact (integer cents).
  - appending a ledger entry stores the expected fields.
  - a direct DELETE on big_ledger raises.
  - an UPDATE other than active->invalidated raises; active->invalidated is allowed.
  - an audit row is append-only.
  - a multi-write plpgsql RPC rolls back fully when any step fails — zero rows persist
    (proves atomicity end-to-end through call_rpc). [HEADLINE GATE]
"""

from decimal import Decimal

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Money — integer cents, no floats (pure unit; no DB)
# ─────────────────────────────────────────────────────────────────────────────


def test_money_stores_cents_as_int():
    from api.treasury.core.money import Money

    assert Money(1234).cents == 1234
    assert Money.from_cents(500).cents == 500


def test_money_rejects_float_construction():
    from api.treasury.core.money import Money

    with pytest.raises(TypeError):
        Money(12.34)


def test_money_rejects_str_construction():
    from api.treasury.core.money import Money

    with pytest.raises(TypeError):
        Money("1234")


def test_money_rejects_bool_construction():
    from api.treasury.core.money import Money

    with pytest.raises(TypeError):
        Money(True)


def test_money_from_numeric_converts_dollars_to_cents():
    from api.treasury.core.money import Money

    assert Money.from_numeric(Decimal("12.34")).cents == 1234
    assert Money.from_numeric("12.34").cents == 1234
    assert Money.from_numeric(0).cents == 0


def test_money_from_numeric_rounds_half_up():
    from api.treasury.core.money import Money

    # 10.005 dollars -> 1000.5 cents -> ROUND_HALF_UP -> 1001
    assert Money.from_numeric("10.005").cents == 1001
    # 0.014 dollars -> 1.4 cents -> 1
    assert Money.from_numeric("0.014").cents == 1


def test_money_arithmetic_is_exact():
    from api.treasury.core.money import Money

    assert Money(100) + Money(50) == Money(150)
    assert Money(100) - Money(150) == Money(-50)
    assert Money(1) + Money(2) + Money(3) == Money(6)


def test_money_rejects_arithmetic_with_non_money():
    from api.treasury.core.money import Money

    with pytest.raises(TypeError):
        Money(100) + 5
    with pytest.raises(TypeError):
        Money(100) + 1.5


def test_money_comparison():
    from api.treasury.core.money import Money

    assert Money(100) < Money(200)
    assert Money(-50) < Money(0)
    assert Money(100) == Money(100)
    assert Money(100) != Money(101)


def test_money_to_dollars_str():
    from api.treasury.core.money import Money

    assert Money(1234).to_dollars_str() == "$12.34"
    assert Money(5).to_dollars_str() == "$0.05"
    assert Money(0).to_dollars_str() == "$0.00"
    assert Money(-1234).to_dollars_str() == "-$12.34"


# ─────────────────────────────────────────────────────────────────────────────
# Clock — injectable, tz-aware UTC (pure unit; no DB)
# ─────────────────────────────────────────────────────────────────────────────


def test_system_clock_returns_tz_aware_utc():
    from datetime import timezone

    from api.treasury.core.clock import SystemClock

    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timezone.utc.utcoffset(None)


def test_fake_clock_returns_fixed_time():
    from datetime import datetime, timezone

    from api.treasury.core.clock import FakeClock

    fixed = datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc)
    clock = FakeClock(fixed)
    assert clock.now() == fixed
    assert clock.now() == fixed  # stable across calls
    assert clock.now().tzinfo is not None


# ─────────────────────────────────────────────────────────────────────────────
# big_ledger — append-only enforced at the DB level (triggers; invariants 1, 4)
# These insert via raw SQL (superuser) to isolate the trigger from the writer.
# ─────────────────────────────────────────────────────────────────────────────


def _insert_ledger_row(cursor, chapter_id, member_id, *, status="active"):
    cursor.execute(
        """
        INSERT INTO big_ledger
            (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
        VALUES (%s, 'INVOICE_CREATED', 1000, %s, 'unpaid_invoices', gen_random_uuid(), %s)
        RETURNING id
        """,
        (chapter_id, member_id, status),
    )
    return str(cursor.fetchone()["id"])


def test_big_ledger_direct_delete_raises(cursor, chapter_id, member_id):
    import psycopg2

    entry_id = _insert_ledger_row(cursor, chapter_id, member_id)
    with pytest.raises(psycopg2.Error):
        cursor.execute("DELETE FROM big_ledger WHERE id = %s", (entry_id,))
    # row still present
    cursor.execute("SELECT 1 FROM big_ledger WHERE id = %s", (entry_id,))
    assert cursor.fetchone() is not None


def test_big_ledger_disallowed_update_raises(cursor, chapter_id, member_id):
    import psycopg2

    entry_id = _insert_ledger_row(cursor, chapter_id, member_id)
    with pytest.raises(psycopg2.Error):
        cursor.execute(
            "UPDATE big_ledger SET amount_cents = 999999 WHERE id = %s", (entry_id,)
        )
    cursor.execute("SELECT amount_cents FROM big_ledger WHERE id = %s", (entry_id,))
    assert cursor.fetchone()["amount_cents"] == 1000


def test_big_ledger_active_to_invalidated_update_allowed(cursor, chapter_id, member_id):
    entry_id = _insert_ledger_row(cursor, chapter_id, member_id)
    cursor.execute(
        "UPDATE big_ledger SET status = 'invalidated' WHERE id = %s", (entry_id,)
    )
    cursor.execute("SELECT status FROM big_ledger WHERE id = %s", (entry_id,))
    assert cursor.fetchone()["status"] == "invalidated"


def test_big_ledger_invalidated_to_active_update_raises(cursor, chapter_id, member_id):
    import psycopg2

    entry_id = _insert_ledger_row(cursor, chapter_id, member_id, status="invalidated")
    with pytest.raises(psycopg2.Error):
        cursor.execute(
            "UPDATE big_ledger SET status = 'active' WHERE id = %s", (entry_id,)
        )


# ─────────────────────────────────────────────────────────────────────────────
# audit_logs — append-only (immutable; invariant 7)
# ─────────────────────────────────────────────────────────────────────────────


def _insert_audit_row(cursor, chapter_id, actor_id):
    cursor.execute(
        """
        INSERT INTO audit_logs (chapter_id, action, actor_id, target_table, target_id, metadata)
        VALUES (%s, 'CREATE_INVOICE', %s, 'unpaid_invoices', gen_random_uuid(), '{}'::jsonb)
        RETURNING id
        """,
        (chapter_id, actor_id),
    )
    return str(cursor.fetchone()["id"])


def test_audit_log_delete_raises(cursor, chapter_id, member_id):
    import psycopg2

    audit_id = _insert_audit_row(cursor, chapter_id, member_id)
    with pytest.raises(psycopg2.Error):
        cursor.execute("DELETE FROM audit_logs WHERE id = %s", (audit_id,))
    cursor.execute("SELECT 1 FROM audit_logs WHERE id = %s", (audit_id,))
    assert cursor.fetchone() is not None


def test_audit_log_update_raises(cursor, chapter_id, member_id):
    import psycopg2

    audit_id = _insert_audit_row(cursor, chapter_id, member_id)
    with pytest.raises(psycopg2.Error):
        cursor.execute(
            "UPDATE audit_logs SET action = 'REBUILD' WHERE id = %s", (audit_id,)
        )


# ─────────────────────────────────────────────────────────────────────────────
# LedgerWriter / AuditLogger — the only sanctioned writers (§2.3)
# ─────────────────────────────────────────────────────────────────────────────


def test_ledger_writer_append_stores_expected_fields(sb_client, cursor, chapter_id, member_id, fake_clock):
    from api.treasury.core.ledger import EntryType, LedgerWriter

    writer = LedgerWriter(sb_client, fake_clock)
    source_id = str(__import__("uuid").uuid4())
    entry = writer.append(
        EntryType.INVOICE_CREATED,
        1500,
        member_id=member_id,
        source_table="unpaid_invoices",
        source_id=source_id,
        chapter_id=chapter_id,
    )

    cursor.execute(
        "SELECT * FROM big_ledger WHERE id = %s", (str(entry.id),)
    )
    row = cursor.fetchone()
    assert row["entry_type"] == "INVOICE_CREATED"
    assert row["amount_cents"] == 1500
    assert str(row["member_id"]) == member_id
    assert row["source_table"] == "unpaid_invoices"
    assert str(row["source_id"]) == source_id
    assert str(row["chapter_id"]) == chapter_id
    assert row["status"] == "active"
    assert row["created_at"] is not None


def test_ledger_writer_invalidate_sets_status_and_metadata(sb_client, cursor, chapter_id, member_id, fake_clock):
    from api.treasury.core.ledger import EntryType, LedgerWriter

    writer = LedgerWriter(sb_client, fake_clock)
    entry = writer.append(
        EntryType.ADJUSTMENT_CREATED,
        -500,
        member_id=member_id,
        source_table="finance_adjustments",
        source_id=str(__import__("uuid").uuid4()),
        chapter_id=chapter_id,
    )
    writer.invalidate(str(entry.id), reason="entered in error", actor_id=member_id)

    cursor.execute(
        "SELECT status, invalidated_reason FROM big_ledger WHERE id = %s", (str(entry.id),)
    )
    row = cursor.fetchone()
    assert row["status"] == "invalidated"
    assert row["invalidated_reason"] == "entered in error"


def test_audit_logger_record_stores_fields(sb_client, cursor, chapter_id, member_id, fake_clock):
    from api.treasury.core.audit import AuditAction, AuditLogger

    logger = AuditLogger(sb_client, fake_clock)
    target_id = str(__import__("uuid").uuid4())
    logger.record(
        AuditAction.CREATE_INVOICE,
        actor_id=member_id,
        target_table="unpaid_invoices",
        target_id=target_id,
        chapter_id=chapter_id,
        metadata={"amount_cents": 1500},
    )

    cursor.execute(
        "SELECT * FROM audit_logs WHERE target_id = %s AND chapter_id = %s",
        (target_id, chapter_id),
    )
    row = cursor.fetchone()
    assert row is not None
    assert row["action"] == "CREATE_INVOICE"
    assert str(row["actor_id"]) == member_id
    assert row["target_table"] == "unpaid_invoices"
    assert row["metadata"] == {"amount_cents": 1500}


def test_call_rpc_rolls_back_multi_write_when_function_raises(sb_client, cursor, chapter_id):
    from api.treasury.db.rpc import call_rpc

    with pytest.raises(Exception):
        call_rpc(
            "tr_test_atomic_rollback",
            {"p_chapter_id": chapter_id, "p_idempotency_key": "chunk0-rollback-test"},
            sb=sb_client,
        )

    cursor.execute("SELECT COUNT(*) AS count FROM big_ledger WHERE chapter_id = %s", (chapter_id,))
    assert cursor.fetchone()["count"] == 0
    cursor.execute("SELECT COUNT(*) AS count FROM audit_logs WHERE chapter_id = %s", (chapter_id,))
    assert cursor.fetchone()["count"] == 0
