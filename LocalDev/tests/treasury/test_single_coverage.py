"""F-029 — invoice coverage lives only in payment_allocations.

A legacy verification (0031) and every paid fine migrated by 0012 stored coverage
on verified_payments.invoice_id; v2 stores it in payment_allocations. Reallocating
a payment that still had the direct link counted its cents twice.
"""

from __future__ import annotations

from pathlib import Path

import psycopg2
import pytest

from api.treasury.core.balance import BalanceEngine
from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc

_MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0165_single_coverage.sql"


def _run_0165_data(cursor):
    """Re-run the data statements of 0165 (they are written to be re-runnable)."""
    sql = _MIGRATION.read_text()
    start = sql.index("-- >>> 0165 data")
    end = sql.index("-- <<< 0165 data")
    cursor.execute(sql[start:end])


def _legacy_paid_invoice(cursor, chapter_id, member_id, amount):
    """A paid invoice covered the way 0012 did it: direct invoice_id, no allocation."""
    cursor.execute(
        """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
           VALUES (%s, %s, 'fine', %s, 'paid') RETURNING id""",
        (chapter_id, member_id, amount),
    )
    invoice_id = str(cursor.fetchone()["id"])
    cursor.execute(
        """INSERT INTO verified_payments
               (chapter_id, member_id, invoice_id, submission_id, amount_cents, verified_by, verified_at)
           VALUES (%s, %s, %s, NULL, %s, NULL, now()) RETURNING id""",
        (chapter_id, member_id, invoice_id, amount),
    )
    return invoice_id, str(cursor.fetchone()["id"])


def _unpaid_invoice(cursor, chapter_id, member_id, amount):
    cursor.execute(
        """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
           VALUES (%s, %s, 'dues', %s, 'unpaid') RETURNING id""",
        (chapter_id, member_id, amount),
    )
    return str(cursor.fetchone()["id"])


def _status(cursor, invoice_id):
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice_id,))
    return cursor.fetchone()["status"]


def _remaining(cursor, invoice_id):
    cursor.execute("SELECT tr_invoice_remaining_cents(%s) AS r", (invoice_id,))
    return cursor.fetchone()["r"]


def test_reallocating_a_directly_covered_payment_does_not_pay_two_invoices(
    cursor, chapter_id, member_id
):
    inv_a, vp = _legacy_paid_invoice(cursor, chapter_id, member_id, 5000)
    inv_b = _unpaid_invoice(cursor, chapter_id, member_id, 5000)
    _run_0165_data(cursor)  # what the migration did to every legacy row

    cursor.execute(
        "SELECT tr_reallocate_payment(%s, %s, %s::jsonb, %s, %s)",
        (chapter_id, vp, f'[{{"invoice_id": "{inv_b}", "amount_cents": 5000}}]',
         member_id, "move to dues"),
    )

    statuses = [_status(cursor, inv_a), _status(cursor, inv_b)]
    assert statuses.count("paid") == 1, statuses
    assert _remaining(cursor, inv_a) == 5000


def test_reallocate_refuses_a_payment_that_still_has_a_direct_link(cursor, chapter_id, member_id):
    _, vp = _legacy_paid_invoice(cursor, chapter_id, member_id, 5000)
    inv_b = _unpaid_invoice(cursor, chapter_id, member_id, 5000)

    with pytest.raises(psycopg2.Error, match="directly"):
        cursor.execute(
            "SELECT tr_reallocate_payment(%s, %s, %s::jsonb, %s, %s)",
            (chapter_id, vp, f'[{{"invoice_id": "{inv_b}", "amount_cents": 5000}}]',
             member_id, "move to dues"),
        )
    assert _status(cursor, inv_b) == "unpaid"


def _figures(sb_client, member_id):
    f = BalanceEngine(sb_client)._member_figures(member_id)
    return {k: int(f[k]) for k in (
        "total_owed_cents", "total_paid_cents", "outstanding_balance_cents", "current_balance_cents")}


def test_migrated_direct_coverage_keeps_balances(sb_client, cursor, chapter_id, member_id):
    inv, vp = _legacy_paid_invoice(cursor, chapter_id, member_id, 2500)
    before = _figures(sb_client, member_id)

    _run_0165_data(cursor)
    _run_0165_data(cursor)  # second run is a no-op

    assert _figures(sb_client, member_id) == before
    assert _status(cursor, inv) == "paid"
    assert _remaining(cursor, inv) == 0
    cursor.execute("SELECT invoice_id FROM verified_payments WHERE id=%s", (vp,))
    assert cursor.fetchone()["invoice_id"] is None
    cursor.execute(
        "SELECT invoice_id, amount_cents FROM payment_allocations WHERE verified_payment_id=%s",
        (vp,),
    )
    rows = cursor.fetchall()
    assert [(str(r["invoice_id"]), r["amount_cents"]) for r in rows] == [(inv, 2500)]


def test_verify_does_not_resurrect_a_cancelled_invoice(sb_client, cursor, chapter_id, member_id, monkeypatch):
    monkeypatch.setattr(inv_svc, "recompute_member_balance", lambda sb, member_id: None)
    invoice = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=4000, description=None, actor_id=member_id,
    )
    sub = inv_svc.submit_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id, invoice_id=invoice["id"],
        claimed_amount_cents=4000, method="venmo", proof_ref=None, actor_id=member_id,
    )
    cursor.execute(
        "SELECT tr_void_invoice(%s, %s, %s, %s)",
        (chapter_id, invoice["id"], member_id, "issued by mistake"),
    )

    pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id
    )

    assert _status(cursor, invoice["id"]) == "cancelled"
