"""Chunk E — Adjustments & Refunds (Slices 9, 10).

Manual corrections that move a balance with a paper trail (adjustments) and the
return of money to a member (refunds). Both are atomic plpgsql RPCs; both leave a
ledger + audit trail; neither is ever hard-deleted (invariant 1 — corrected via a
new adjustment / via invalidation).

Every assertion is chapter-scoped; the append-only demo tables accumulate.
"""

from __future__ import annotations

import psycopg2
import pytest

from api.treasury.services import adjustments as adj_svc
from api.treasury.services import balance as bal_svc
from api.treasury.services import expenses as exp_svc
from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc
from api.treasury.services import refunds as ref_svc


def _overpaid_verified_payment(sb, chapter_id, member_id, *, invoice_cents, paid_cents):
    """Set up a member who overpaid an invoice; return their verified_payment row."""
    invoice = inv_svc.create_invoice(
        sb, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=invoice_cents, description=None, actor_id=member_id,
    )
    submission = inv_svc.submit_payment(
        sb, chapter_id=chapter_id, member_id=member_id, invoice_id=invoice["id"],
        claimed_amount_cents=paid_cents, method="venmo", proof_ref="ref-1",
        actor_id=member_id,
    )
    return pay_svc.verify_payment(
        sb, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )


# ── helpers ──────────────────────────────────────────────────────────────────
def _ledger(cursor, chapter_id, source_id):
    cursor.execute(
        "SELECT * FROM big_ledger WHERE chapter_id=%s AND source_id=%s ORDER BY created_at",
        (chapter_id, source_id),
    )
    return cursor.fetchall()


# ── Slice 9: adjustments ─────────────────────────────────────────────────────
def test_member_adjustment_writes_ledger_and_audit(sb_client, cursor, chapter_id, member_id):
    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        kind="manual_correction", delta_cents=-1500, reason="goodwill credit",
        officer_id=member_id,
    )
    assert adj["status"] == "active"
    assert adj["delta_cents"] == -1500

    ledger = _ledger(cursor, chapter_id, adj["id"])
    assert len(ledger) == 1
    assert ledger[0]["entry_type"] == "ADJUSTMENT_CREATED"
    assert ledger[0]["amount_cents"] == -1500
    assert str(ledger[0]["member_id"]) == str(member_id)

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND target_id=%s AND action='CREATE_ADJUSTMENT'",
        (chapter_id, adj["id"]),
    )
    assert cursor.fetchone()["n"] == 1


def test_member_adjustment_changes_member_outstanding_by_delta(sb_client, cursor, chapter_id, member_id):
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    before = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert before["outstanding_balance_cents"] == 5000

    adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        kind="dues_forgiveness", delta_cents=-2000, reason="hardship forgiveness",
        officer_id=member_id,
    )
    after = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert after["outstanding_balance_cents"] == 3000
    assert after["current_balance_cents"] == 3000


def test_chapter_adjustment_changes_only_chapter_balance(sb_client, cursor, chapter_id, member_id):
    # Member has an invoice; snapshot their balance.
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    member_before = bal_svc.get_member_balance(sb_client, member_id=member_id)
    chapter_before = exp_svc.chapter_balance(sb_client, chapter_id=chapter_id)

    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=None,
        kind="manual_correction", delta_cents=3000, reason="found cash in safe",
        officer_id=member_id,
    )
    assert adj["member_id"] is None

    # Chapter balance moved by the delta; the member's balance is untouched.
    chapter_after = exp_svc.chapter_balance(sb_client, chapter_id=chapter_id)
    assert chapter_after.cents == chapter_before.cents + 3000

    member_after = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert member_after["current_balance_cents"] == member_before["current_balance_cents"]


def test_missing_reason_is_rejected(sb_client, chapter_id, member_id):
    with pytest.raises(Exception):
        adj_svc.create_adjustment(
            sb_client, chapter_id=chapter_id, member_id=member_id,
            kind="manual_correction", delta_cents=-100, reason="   ",
            officer_id=member_id,
        )


def test_missing_officer_is_rejected(sb_client, chapter_id, member_id):
    with pytest.raises(Exception):
        adj_svc.create_adjustment(
            sb_client, chapter_id=chapter_id, member_id=member_id,
            kind="manual_correction", delta_cents=-100, reason="valid reason",
            officer_id=None,
        )


# ── Slice 10: refunds ────────────────────────────────────────────────────────
def test_refund_reduces_member_credit_and_chapter_balance(sb_client, cursor, chapter_id, member_id):
    vp = _overpaid_verified_payment(sb_client, chapter_id, member_id, invoice_cents=5000, paid_cents=7000)

    member_before = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert member_before["current_balance_cents"] == -2000  # $20 credit
    chapter_before = exp_svc.chapter_balance(sb_client, chapter_id=chapter_id)
    assert chapter_before.cents == 7000

    refund = ref_svc.issue_refund(
        sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
        amount_cents=2000, reason="return overpayment", officer_id=member_id,
    )
    assert refund["status"] == "active"
    assert refund["amount_cents"] == 2000
    assert str(refund["member_id"]) == str(member_id)

    # Member credit fully returned; chapter balance decreased by the refund.
    member_after = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert member_after["current_balance_cents"] == 0
    chapter_after = exp_svc.chapter_balance(sb_client, chapter_id=chapter_id)
    assert chapter_after.cents == 5000

    ledger = _ledger(cursor, chapter_id, refund["id"])
    assert len(ledger) == 1
    assert ledger[0]["entry_type"] == "REFUND_ISSUED"
    assert ledger[0]["amount_cents"] == -2000
    assert str(ledger[0]["member_id"]) == str(member_id)

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND target_id=%s AND action='ISSUE_REFUND'",
        (chapter_id, refund["id"]),
    )
    assert cursor.fetchone()["n"] == 1


def test_refund_cannot_exceed_source_payment(sb_client, chapter_id, member_id):
    vp = _overpaid_verified_payment(sb_client, chapter_id, member_id, invoice_cents=5000, paid_cents=7000)
    with pytest.raises(Exception):
        ref_svc.issue_refund(
            sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
            amount_cents=7001, reason="too much", officer_id=member_id,
        )


def test_partial_refunds_cannot_aggregate_past_source(sb_client, chapter_id, member_id):
    vp = _overpaid_verified_payment(sb_client, chapter_id, member_id, invoice_cents=5000, paid_cents=7000)
    ref_svc.issue_refund(
        sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
        amount_cents=5000, reason="first slice", officer_id=member_id,
    )
    # 5000 already refunded against a 7000 payment; a further 2001 would exceed it.
    with pytest.raises(Exception):
        ref_svc.issue_refund(
            sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
            amount_cents=2001, reason="over the top", officer_id=member_id,
        )


def test_retried_refund_does_not_double_pay(sb_client, cursor, chapter_id, member_id):
    vp = _overpaid_verified_payment(sb_client, chapter_id, member_id, invoice_cents=5000, paid_cents=7000)
    first = ref_svc.issue_refund(
        sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
        amount_cents=2000, reason="return overpayment", officer_id=member_id,
        idempotency_key="refund-key-1",
    )
    second = ref_svc.issue_refund(
        sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
        amount_cents=2000, reason="return overpayment", officer_id=member_id,
        idempotency_key="refund-key-1",
    )
    assert first["id"] == second["id"]
    cursor.execute(
        "SELECT count(*) AS n FROM refunds WHERE verified_payment_id=%s", (vp["id"],)
    )
    assert cursor.fetchone()["n"] == 1


def test_refund_cannot_be_hard_deleted(sb_client, cursor, chapter_id, member_id):
    vp = _overpaid_verified_payment(sb_client, chapter_id, member_id, invoice_cents=5000, paid_cents=7000)
    refund = ref_svc.issue_refund(
        sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
        amount_cents=2000, reason="return overpayment", officer_id=member_id,
    )
    with pytest.raises(psycopg2.Error):
        cursor.execute("DELETE FROM refunds WHERE id=%s", (refund["id"],))


# ── Slice 9 governance: two-officer sign-off above a threshold ───────────────
def test_over_threshold_adjustment_requires_second_signoff(sb_client, cursor, chapter_id, member_id, member_factory):
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=200000, description=None, actor_id=member_id,
    )
    before = bal_svc.get_member_balance(sb_client, member_id=member_id)

    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        kind="dues_forgiveness", delta_cents=-100000, reason="large waive",
        officer_id=member_id, threshold_cents=50000,
    )
    assert adj["status"] == "pending"

    # A pending adjustment has NO balance effect and NO ledger entry yet.
    mid = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert mid["current_balance_cents"] == before["current_balance_cents"]
    assert len(_ledger(cursor, chapter_id, adj["id"])) == 0

    approver = member_factory()
    activated = adj_svc.approve_adjustment(
        sb_client, chapter_id=chapter_id, adjustment_id=adj["id"], approver_id=approver
    )
    assert activated["status"] == "active"
    assert str(activated["approved_by"]) == str(approver)

    after = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert after["current_balance_cents"] == before["current_balance_cents"] - 100000
    ledger = _ledger(cursor, chapter_id, adj["id"])
    assert len(ledger) == 1 and ledger[0]["entry_type"] == "ADJUSTMENT_CREATED"


def test_over_threshold_adjustment_cannot_be_self_approved(sb_client, chapter_id, member_id):
    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        kind="manual_correction", delta_cents=-90000, reason="large waive",
        officer_id=member_id, threshold_cents=50000,
    )
    assert adj["status"] == "pending"
    with pytest.raises(Exception):
        adj_svc.approve_adjustment(
            sb_client, chapter_id=chapter_id, adjustment_id=adj["id"], approver_id=member_id
        )


# ── permission gating: refund requires treasury:refund:create ────────────────
# 0147 folded treasury_grants into the central catalog: authority is a role in
# member_roles carrying the key, never a per-member grant row.
async def test_refund_requires_refund_create_permission(sb_client, cursor, chapter_id, member_id, monkeypatch):
    from fastapi import HTTPException

    import api.rbac.services.permissions as rbac_permissions
    from api.rbac.auth import require_permission
    from api.treasury.api import refunds

    monkeypatch.setattr(rbac_permissions, "get_db", lambda: sb_client)
    dep = require_permission(refunds.REFUND_CREATE)
    user = {"id": member_id, "chapter_id": chapter_id, "role": "member"}

    # A plain member holds no role granting the key → refused.
    with pytest.raises(HTTPException) as exc:
        await dep(user=user)
    assert exc.value.status_code == 403

    # Assign the treasurer role → the same call now passes.
    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s,%s,'treasurer') "
        "ON CONFLICT DO NOTHING",
        (chapter_id, member_id),
    )
    assert await dep(user=user) == user


# ── F-030 / D3: a refund reopens the invoice it covered ──────────────────────
def _paid_invoice(sb, chapter_id, member_id, *, invoice_cents, paid_cents):
    invoice = inv_svc.create_invoice(
        sb, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=invoice_cents, description=None, actor_id=member_id,
    )
    submission = inv_svc.submit_payment(
        sb, chapter_id=chapter_id, member_id=member_id, invoice_id=invoice["id"],
        claimed_amount_cents=paid_cents, method="venmo", proof_ref="ref-1",
        actor_id=member_id,
    )
    vp = pay_svc.verify_payment_v2(
        sb, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    return invoice, vp


def _refund(sb, chapter_id, member_id, vp, cents):
    return ref_svc.issue_refund(
        sb, chapter_id=chapter_id, verified_payment_id=vp["id"], amount_cents=cents,
        reason="refund", officer_id=member_id,
    )


def _status_and_remaining(cursor, invoice_id):
    cursor.execute(
        "SELECT status, tr_invoice_remaining_cents(id) AS remaining FROM unpaid_invoices WHERE id=%s",
        (invoice_id,),
    )
    row = cursor.fetchone()
    return row["status"], row["remaining"]


def test_full_refund_reopens_the_invoice(sb_client, cursor, chapter_id, member_id):
    invoice, vp = _paid_invoice(sb_client, chapter_id, member_id, invoice_cents=10000, paid_cents=10000)
    assert _status_and_remaining(cursor, invoice["id"]) == ("paid", 0)

    _refund(sb_client, chapter_id, member_id, vp, 10000)

    assert _status_and_remaining(cursor, invoice["id"]) == ("unpaid", 10000)
    assert bal_svc.get_member_balance(sb_client, member_id=member_id)["outstanding_balance_cents"] == 10000


def test_partial_refund_makes_invoice_partially_paid(sb_client, cursor, chapter_id, member_id):
    invoice, vp = _paid_invoice(sb_client, chapter_id, member_id, invoice_cents=10000, paid_cents=10000)

    _refund(sb_client, chapter_id, member_id, vp, 4000)

    assert _status_and_remaining(cursor, invoice["id"]) == ("partially_paid", 4000)


def test_refund_of_unallocated_credit_changes_no_invoice(sb_client, cursor, chapter_id, member_id):
    invoice, vp = _paid_invoice(sb_client, chapter_id, member_id, invoice_cents=10000, paid_cents=15000)

    _refund(sb_client, chapter_id, member_id, vp, 5000)

    assert _status_and_remaining(cursor, invoice["id"]) == ("paid", 0)
    cursor.execute(
        "SELECT count(*) AS n FROM payment_allocations WHERE verified_payment_id=%s AND reverses_allocation_id IS NOT NULL",
        (vp["id"],),
    )
    assert cursor.fetchone()["n"] == 0


def test_second_refund_reverses_only_what_credit_no_longer_covers(sb_client, cursor, chapter_id, member_id):
    invoice, vp = _paid_invoice(sb_client, chapter_id, member_id, invoice_cents=10000, paid_cents=15000)

    _refund(sb_client, chapter_id, member_id, vp, 3000)  # 2000 credit left
    assert _status_and_remaining(cursor, invoice["id"]) == ("paid", 0)
    _refund(sb_client, chapter_id, member_id, vp, 4000)  # 2000 from credit, 2000 reopened

    assert _status_and_remaining(cursor, invoice["id"]) == ("partially_paid", 2000)


def test_refund_does_not_touch_cancelled_invoice(sb_client, cursor, chapter_id, member_id):
    invoice, vp = _paid_invoice(sb_client, chapter_id, member_id, invoice_cents=10000, paid_cents=4000)
    cursor.execute(
        "SELECT tr_void_invoice(%s, %s, %s, %s)",
        (chapter_id, invoice["id"], member_id, "issued by mistake"),
    )

    _refund(sb_client, chapter_id, member_id, vp, 4000)

    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice["id"],))
    assert cursor.fetchone()["status"] == "cancelled"
