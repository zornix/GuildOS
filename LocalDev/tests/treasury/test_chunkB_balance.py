"""Chunk B — Member Balance Engine (Slice 5).

Balances derive from operational tables only and are provably independent of the ledger.
"""

from __future__ import annotations

from api.treasury.core.balance import BalanceEngine
from api.treasury.services import balance as svc


def _invoice(cursor, chapter_id, member_id, amount_cents, status="unpaid"):
    cursor.execute(
        """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
           VALUES (%s,%s,'dues',%s,%s) RETURNING id""",
        (chapter_id, member_id, amount_cents, status),
    )
    return str(cursor.fetchone()["id"])


def _verified_payment(cursor, chapter_id, member_id, invoice_id, amount_cents):
    cursor.execute(
        """INSERT INTO verified_payments (chapter_id, member_id, invoice_id, amount_cents, verified_at)
           VALUES (%s,%s,%s,%s, now())""",
        (chapter_id, member_id, invoice_id, amount_cents),
    )


# ── formula across the four cases ────────────────────────────────────────────
def test_owed_only(sb_client, cursor, chapter_id, member_id):
    _invoice(cursor, chapter_id, member_id, 5000)
    eng = BalanceEngine(sb_client)
    figs = eng._member_figures(member_id)
    assert figs["total_owed_cents"] == 5000
    assert figs["total_paid_cents"] == 0
    assert figs["outstanding_balance_cents"] == 5000
    assert figs["current_balance_cents"] == 5000


def test_partial_payment(sb_client, cursor, chapter_id, member_id):
    inv = _invoice(cursor, chapter_id, member_id, 5000)
    _verified_payment(cursor, chapter_id, member_id, inv, 2000)
    figs = BalanceEngine(sb_client)._member_figures(member_id)
    assert figs["outstanding_balance_cents"] == 3000
    assert figs["current_balance_cents"] == 3000


def test_fully_paid(sb_client, cursor, chapter_id, member_id):
    inv = _invoice(cursor, chapter_id, member_id, 5000, status="paid")
    _verified_payment(cursor, chapter_id, member_id, inv, 5000)
    figs = BalanceEngine(sb_client)._member_figures(member_id)
    assert figs["outstanding_balance_cents"] == 0
    assert figs["current_balance_cents"] == 0


def test_overpaid_is_credit(sb_client, cursor, chapter_id, member_id):
    inv = _invoice(cursor, chapter_id, member_id, 5000, status="paid")
    _verified_payment(cursor, chapter_id, member_id, inv, 7000)
    figs = BalanceEngine(sb_client)._member_figures(member_id)
    assert figs["outstanding_balance_cents"] == 0  # floored at 0
    assert figs["current_balance_cents"] == -2000  # negative = credit


def test_member_outstanding_returns_money(sb_client, cursor, chapter_id, member_id):
    _invoice(cursor, chapter_id, member_id, 4200)
    out = BalanceEngine(sb_client).member_outstanding(member_id)
    assert out.cents == 4200


# ── ledger-independence (the signature test, invariant 3) ────────────────────
def test_balance_is_independent_of_the_ledger(sb_client, cursor, chapter_id, member_id):
    inv = _invoice(cursor, chapter_id, member_id, 5000)
    _verified_payment(cursor, chapter_id, member_id, inv, 2000)
    eng = BalanceEngine(sb_client)
    eng.recompute_member(member_id)
    before = svc.get_member_balance(sb_client, member_id=member_id)

    # Corrupt the ledger with a wildly wrong member-scoped entry.
    cursor.execute(
        """INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, source_table, source_id, status)
           VALUES (%s,'PAYMENT_RECEIVED', 999999, %s, 'unpaid_invoices', %s, 'active')""",
        (chapter_id, member_id, inv),
    )
    eng.recompute_member(member_id)
    after = svc.get_member_balance(sb_client, member_id=member_id)

    assert after["outstanding_balance_cents"] == before["outstanding_balance_cents"] == 3000


# ── cache == freshly computed ────────────────────────────────────────────────
def test_cache_equals_freshly_computed(sb_client, cursor, chapter_id, member_id):
    inv = _invoice(cursor, chapter_id, member_id, 8000)
    _verified_payment(cursor, chapter_id, member_id, inv, 3000)
    eng = BalanceEngine(sb_client)
    eng.recompute_member(member_id)

    cursor.execute(
        "SELECT * FROM member_finance_accounts WHERE member_id=%s", (member_id,)
    )
    cached = cursor.fetchone()
    fresh = eng._member_figures(member_id)
    assert cached["outstanding_balance_cents"] == fresh["outstanding_balance_cents"] == 5000
    assert cached["current_balance_cents"] == fresh["current_balance_cents"] == 5000
    assert cached["total_owed_cents"] == 8000
    assert cached["total_paid_cents"] == 3000


# ── recompute_all reproduces every cached row ────────────────────────────────
def test_recompute_all_reproduces_every_row(sb_client, cursor, chapter_id, member_factory):
    m1, m2 = member_factory(), member_factory()
    _invoice(cursor, chapter_id, m1, 5000)
    inv2 = _invoice(cursor, chapter_id, m2, 9000)
    _verified_payment(cursor, chapter_id, m2, inv2, 4000)

    BalanceEngine(sb_client).recompute_all(chapter_id)

    cursor.execute(
        "SELECT member_id, outstanding_balance_cents FROM member_finance_accounts WHERE chapter_id=%s",
        (chapter_id,),
    )
    rows = {str(r["member_id"]): r["outstanding_balance_cents"] for r in cursor.fetchall()}
    assert rows[m1] == 5000
    assert rows[m2] == 5000
