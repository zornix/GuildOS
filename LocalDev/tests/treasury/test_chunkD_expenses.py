"""Chunk D — Expenses & Chapter Balance (Slices 7, 8).

Expenses move ONLY the chapter balance; member balances are untouched.
"""

from __future__ import annotations

import pytest

from api.treasury.services import expenses as svc


def _insert_verified_payment(cursor, chapter_id, member_id, amount_cents):
    cursor.execute(
        """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
           VALUES (%s,%s,'dues',%s,'paid') RETURNING id""",
        (chapter_id, member_id, amount_cents),
    )
    invoice_id = cursor.fetchone()["id"]
    cursor.execute(
        """INSERT INTO verified_payments (chapter_id, member_id, invoice_id, amount_cents, verified_at)
           VALUES (%s,%s,%s,%s, now())""",
        (chapter_id, member_id, invoice_id, amount_cents),
    )


def _ledger(cursor, chapter_id, source_id):
    cursor.execute(
        "SELECT * FROM big_ledger WHERE chapter_id=%s AND source_id=%s ORDER BY created_at",
        (chapter_id, source_id),
    )
    return cursor.fetchall()


# ── Slice 7: create expense + chapter balance ────────────────────────────────
def test_create_expense_persists_active_with_ledger_and_audit(sb_client, cursor, chapter_id, member_id):
    exp = svc.create_expense(
        sb_client, chapter_id=chapter_id, category="supplies",
        amount_cents=3000, description="cups", actor_id=member_id,
    )
    assert exp["status"] == "active"
    assert exp["amount_cents"] == 3000

    ledger = _ledger(cursor, chapter_id, exp["id"])
    assert len(ledger) == 1
    assert ledger[0]["entry_type"] == "EXPENSE_APPROVED"
    assert ledger[0]["amount_cents"] == -3000

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND target_id=%s AND action='CREATE_EXPENSE'",
        (chapter_id, exp["id"]),
    )
    assert cursor.fetchone()["n"] == 1


def test_expense_decreases_chapter_balance(sb_client, cursor, chapter_id, member_id):
    _insert_verified_payment(cursor, chapter_id, member_id, 10000)
    before = svc.chapter_balance(sb_client, chapter_id=chapter_id)
    assert before.cents == 10000

    svc.create_expense(
        sb_client, chapter_id=chapter_id, category="event",
        amount_cents=3000, description=None, actor_id=member_id,
    )
    after = svc.chapter_balance(sb_client, chapter_id=chapter_id)
    assert after.cents == 7000


def test_no_member_balance_changes_from_an_expense(sb_client, cursor, chapter_id, member_id):
    exp = svc.create_expense(
        sb_client, chapter_id=chapter_id, category="maintenance",
        amount_cents=4200, description=None, actor_id=member_id,
    )
    # The expense ledger entry is chapter-scoped: member_id is NULL, so no member's
    # operational footprint changed.
    ledger = _ledger(cursor, chapter_id, exp["id"])
    assert all(r["member_id"] is None for r in ledger)
    cursor.execute(
        "SELECT count(*) AS n FROM big_ledger WHERE chapter_id=%s AND member_id=%s",
        (chapter_id, member_id),
    )
    assert cursor.fetchone()["n"] == 0


# ── Slice 8: invalidate expense ──────────────────────────────────────────────
def test_invalidate_expense_is_non_destructive_and_reversible(sb_client, cursor, chapter_id, member_id):
    _insert_verified_payment(cursor, chapter_id, member_id, 10000)
    exp = svc.create_expense(
        sb_client, chapter_id=chapter_id, category="supplies",
        amount_cents=3000, description=None, actor_id=member_id,
    )
    assert svc.chapter_balance(sb_client, chapter_id=chapter_id).cents == 7000

    inv = svc.invalidate_expense(sb_client, chapter_id=chapter_id, expense_id=exp["id"], actor_id=member_id)
    assert inv["status"] == "invalidated"

    # Original expense row still present.
    cursor.execute("SELECT status FROM chapter_expenses WHERE id=%s", (exp["id"],))
    assert cursor.fetchone()["status"] == "invalidated"

    ledger = _ledger(cursor, chapter_id, exp["id"])
    types = [r["entry_type"] for r in ledger]
    assert "EXPENSE_APPROVED" in types and "EXPENSE_REVERSED" in types

    approved = next(r for r in ledger if r["entry_type"] == "EXPENSE_APPROVED")
    reversed_ = next(r for r in ledger if r["entry_type"] == "EXPENSE_REVERSED")
    assert str(reversed_["reverses_entry_id"]) == str(approved["id"])
    # Net active ledger effect for the pair is zero.
    assert approved["amount_cents"] + reversed_["amount_cents"] == 0

    # Chapter balance returns to its pre-expense value.
    assert svc.chapter_balance(sb_client, chapter_id=chapter_id).cents == 10000

    audit_count = cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE target_id=%s AND action='INVALIDATE_EXPENSE'", (exp["id"],)
    )
    assert cursor.fetchone()["n"] == 1


def test_invalidate_is_idempotent(sb_client, chapter_id, member_id):
    exp = svc.create_expense(
        sb_client, chapter_id=chapter_id, category="supplies",
        amount_cents=3000, description=None, actor_id=member_id,
    )
    svc.invalidate_expense(sb_client, chapter_id=chapter_id, expense_id=exp["id"], actor_id=member_id)
    again = svc.invalidate_expense(sb_client, chapter_id=chapter_id, expense_id=exp["id"], actor_id=member_id)
    assert again["status"] == "invalidated"
