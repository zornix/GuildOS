"""F-031 / D10 — amount and owner columns on money rows cannot be edited in place.

Balances are computed from these rows, so an in-place UPDATE would rewrite what a
member owes with no ledger or audit row. Status transitions the RPCs perform
(invoice status, adjustment pending → active) still work.
"""

from __future__ import annotations

import psycopg2
import pytest

from api.treasury.services import adjustments as adj_svc
from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc
from api.treasury.services import refunds as ref_svc


@pytest.fixture
def rows(sb_client, chapter_id, member_id):
    invoice = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    sub = pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=3000, method="venmo", proof_ref=None,
    )
    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id
    )
    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="manual_correction",
        delta_cents=-500, reason="goodwill", officer_id=member_id,
    )
    refund = ref_svc.issue_refund(
        sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"], amount_cents=1000,
        reason="refund", officer_id=member_id,
    )
    return {"invoice": invoice["id"], "vp": vp["id"], "adj": adj["id"], "refund": refund["id"]}


@pytest.mark.parametrize(
    "table, key, assignment",
    [
        ("verified_payments", "vp", "amount_cents = amount_cents + 100000"),
        ("verified_payments", "vp", "member_id = %(other)s"),
        ("finance_adjustments", "adj", "delta_cents = -999999"),
        ("refunds", "refund", "amount_cents = 1"),
        ("unpaid_invoices", "invoice", "amount_cents = 1"),
        ("unpaid_invoices", "invoice", "member_id = %(other)s"),
    ],
)
def test_money_column_is_frozen(cursor, rows, member_factory, table, key, assignment):
    other = member_factory()
    with pytest.raises(psycopg2.Error, match="frozen"):
        cursor.execute(
            f"UPDATE {table} SET {assignment} WHERE id = %(id)s",
            {"id": rows[key], "other": other},
        )


def test_invoice_status_can_still_change(cursor, rows):
    cursor.execute("UPDATE unpaid_invoices SET status = 'paid' WHERE id = %s", (rows["invoice"],))
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id = %s", (rows["invoice"],))
    assert cursor.fetchone()["status"] == "paid"


def test_adjustment_can_still_go_pending_to_active(sb_client, chapter_id, member_id, member_factory):
    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        kind="dues_forgiveness", delta_cents=-100000, reason="large waive",
        officer_id=member_id, threshold_cents=50000,
    )
    assert adj["status"] == "pending"

    activated = adj_svc.approve_adjustment(
        sb_client, chapter_id=chapter_id, adjustment_id=adj["id"], approver_id=member_factory()
    )
    assert activated["status"] == "active"
