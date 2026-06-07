"""Chunk F-complete — Dashboard, Statement, Exports (Slices 13 + 14).

Read surfaces over the data the write slices produce:
  - dashboard_summary: a single treasurer aggregate.
  - member_statement: a member's chronological invoices/payments/adjustments/refunds.
  - period_report_csv: CSV exports reconciling to the operational tables for a period.

Every assertion is chapter-scoped (conftest §3.4): the shared demo's append-only
tables accumulate and cannot be truncated, so we only inspect rows we created in
the fixture chapter and never assert global COUNT(*).
"""

from __future__ import annotations

import csv
import io

import pytest

from api.treasury.services import adjustments as adj_svc
from api.treasury.services import expenses as exp_svc
from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc
from api.treasury.services import refunds as ref_svc
from api.treasury.services import reports as svc


# ── helpers ──────────────────────────────────────────────────────────────────
def _verified_payment(sb, chapter_id, member_id, *, invoice_cents, paid_cents):
    """Create an invoice, submit, and verify a payment; return (invoice, vp)."""
    invoice = inv_svc.create_invoice(
        sb, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=invoice_cents, description=None, actor_id=member_id,
    )
    submission = inv_svc.submit_payment(
        sb, chapter_id=chapter_id, member_id=member_id, invoice_id=invoice["id"],
        claimed_amount_cents=paid_cents, method="venmo", proof_ref="ref-1",
        actor_id=member_id,
    )
    vp = pay_svc.verify_payment(
        sb, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    return invoice, vp


# ════════════════════════════════════════════════════════════════════════════
# Dashboard
# ════════════════════════════════════════════════════════════════════════════
def test_dashboard_aggregates_match_independent_computation(
    sb_client, cursor, chapter_id, member_factory
):
    """Dashboard figures equal independently computed chapter-scoped numbers."""
    m1 = member_factory()
    m2 = member_factory()
    m3 = member_factory()

    # m1: invoice $50, paid $50 in full → balance 0, chapter cash +5000
    _verified_payment(sb_client, chapter_id, m1, invoice_cents=5000, paid_cents=5000)
    # m2: invoice $80, unpaid → outstanding 8000
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=m2, kind="dues",
        amount_cents=8000, description=None, actor_id=m2,
    )
    # m3: invoice $30 with a pending submission (a pending proof, no money moved)
    inv3 = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=m3, kind="dues",
        amount_cents=3000, description=None, actor_id=m3,
    )
    inv_svc.submit_payment(
        sb_client, chapter_id=chapter_id, member_id=m3, invoice_id=inv3["id"],
        claimed_amount_cents=3000, method="zelle", proof_ref="p3", actor_id=m3,
    )
    # A chapter expense $20 → chapter cash 5000 - 2000 = 3000
    exp_svc.create_expense(
        sb_client, chapter_id=chapter_id, category="supplies",
        amount_cents=2000, description="cups", actor_id=m1,
    )

    summary = svc.dashboard_summary(sb_client, chapter_id=chapter_id)

    # chapter cash balance
    assert summary["chapter_balance_cents"] == 3000
    # total outstanding = Σ outstanding over member accounts (m2 owes 8000, m3 owes 3000)
    assert summary["total_outstanding_cents"] == 11000
    # one pending proof (m3's submission)
    assert summary["pending_proof_count"] == 1
    # members with balance > 0: m2 and m3
    assert summary["members_with_balance_count"] == 2
    # overdue invoices: m2 + m3 invoices are unpaid (not cancelled, not paid)
    assert summary["overdue_invoice_count"] == 2


def test_dashboard_recent_payments_and_expenses_are_chapter_scoped(
    sb_client, cursor, chapter_id, member_factory
):
    """Recent payments/expenses lists contain only this chapter's rows."""
    m1 = member_factory()
    _invoice, vp = _verified_payment(sb_client, chapter_id, m1, invoice_cents=4000, paid_cents=4000)
    exp = exp_svc.create_expense(
        sb_client, chapter_id=chapter_id, category="event",
        amount_cents=1500, description="venue", actor_id=m1,
    )

    summary = svc.dashboard_summary(sb_client, chapter_id=chapter_id)

    recent_payment_ids = {r["id"] for r in summary["recent_payments"]}
    recent_expense_ids = {r["id"] for r in summary["recent_expenses"]}
    assert vp["id"] in recent_payment_ids
    assert exp["id"] in recent_expense_ids
    assert all(r["chapter_id"] == chapter_id for r in summary["recent_payments"])
    assert all(r["chapter_id"] == chapter_id for r in summary["recent_expenses"])


# ════════════════════════════════════════════════════════════════════════════
# Member statement
# ════════════════════════════════════════════════════════════════════════════
def test_statement_contains_all_event_types_chronologically(
    sb_client, cursor, chapter_id, member_factory
):
    """Statement lists invoices, payments, adjustments, refunds in time order."""
    m1 = member_factory()
    invoice, vp = _verified_payment(sb_client, chapter_id, m1, invoice_cents=5000, paid_cents=7000)
    # member overpaid → -2000 credit; issue a refund of the credit
    refund = ref_svc.issue_refund(
        sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
        amount_cents=2000, reason="return overpayment", officer_id=m1,
    )
    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=m1,
        kind="manual_correction", delta_cents=-500, reason="goodwill", officer_id=m1,
    )

    statement = svc.member_statement(sb_client, member_id=m1)

    kinds = {e["type"] for e in statement["entries"]}
    assert {"invoice", "payment", "refund", "adjustment"} <= kinds

    ids_by_type = {}
    for e in statement["entries"]:
        ids_by_type.setdefault(e["type"], set()).add(e["id"])
    assert invoice["id"] in ids_by_type["invoice"]
    assert vp["id"] in ids_by_type["payment"]
    assert refund["id"] in ids_by_type["refund"]
    assert adj["id"] in ids_by_type["adjustment"]

    # chronological by occurred_at
    occurreds = [e["occurred_at"] for e in statement["entries"]]
    assert occurreds == sorted(occurreds)

    # current owed/credit reflects the engine: owed 5000 - paid 7000 + adj -500 + refund 2000
    # = -500 → still a $5 credit
    assert statement["current_balance_cents"] == -500


def test_statement_is_scoped_to_one_member(
    sb_client, cursor, chapter_id, member_factory
):
    """A member's statement never includes another member's rows."""
    m1 = member_factory()
    m2 = member_factory()
    inv1 = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=m1, kind="dues",
        amount_cents=1000, description=None, actor_id=m1,
    )
    inv2 = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=m2, kind="dues",
        amount_cents=2000, description=None, actor_id=m2,
    )

    statement = svc.member_statement(sb_client, member_id=m1)
    entry_ids = {e["id"] for e in statement["entries"]}
    assert inv1["id"] in entry_ids
    assert inv2["id"] not in entry_ids


def test_statement_excludes_pending_adjustments(
    sb_client, cursor, chapter_id, member_factory
):
    """A pending (over-threshold) adjustment has no balance effect (deviation #12).

    It also has no ledger row; the statement reflects only active financial events,
    so the current balance must match the engine (which ignores pending adjustments).
    """
    m1 = member_factory()
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=m1, kind="dues",
        amount_cents=200000, description=None, actor_id=m1,
    )
    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=m1,
        kind="dues_forgiveness", delta_cents=-100000, reason="large waive",
        officer_id=m1, threshold_cents=50000,
    )
    assert adj["status"] == "pending"

    statement = svc.member_statement(sb_client, member_id=m1)
    # Pending adjustment must not move the current balance.
    assert statement["current_balance_cents"] == 200000


# ════════════════════════════════════════════════════════════════════════════
# Period CSV report
# ════════════════════════════════════════════════════════════════════════════
def _parse_csv(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


def test_report_payments_csv_reconciles_to_period(
    sb_client, cursor, chapter_id, member_factory
):
    """The verified_payments CSV for the period contains exactly this chapter's
    verified payments, with amounts matching the operational table."""
    m1 = member_factory()
    _inv, vp = _verified_payment(sb_client, chapter_id, m1, invoice_cents=6000, paid_cents=6000)

    # Determine the period (YYYY-MM) the payment landed in from its created_at.
    cursor.execute("SELECT created_at FROM verified_payments WHERE id=%s", (vp["id"],))
    created = cursor.fetchone()["created_at"]
    period = f"{created.year:04d}-{created.month:02d}"

    csv_text = svc.period_report_csv(
        sb_client, chapter_id=chapter_id, period=period, dataset="payments"
    )
    rows = _parse_csv(csv_text)
    by_id = {r["id"]: r for r in rows}
    assert vp["id"] in by_id
    assert int(by_id[vp["id"]]["amount_cents"]) == 6000
    # every row is chapter-scoped
    assert all(r["chapter_id"] == chapter_id for r in rows)


def test_report_respects_chapter_scope(
    sb_client, cursor, chapter_id, member_factory
):
    """A payment in another chapter never appears in this chapter's report."""
    import uuid as _uuid

    m1 = member_factory()
    _inv, vp = _verified_payment(sb_client, chapter_id, m1, invoice_cents=5000, paid_cents=5000)

    # Build a separate chapter + member + verified payment.
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES (%s,'O','U') RETURNING id",
        (f"other-{_uuid.uuid4()}",),
    )
    other_chapter = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO members (chapter_id, name, email, role, status) "
        "VALUES (%s,%s,%s,'member','active') RETURNING id",
        (other_chapter, f"M-{_uuid.uuid4().hex[:8]}", f"{_uuid.uuid4()}@o.local"),
    )
    other_member = str(cursor.fetchone()["id"])
    _oinv, ovp = _verified_payment(sb_client, other_chapter, other_member, invoice_cents=5000, paid_cents=5000)

    cursor.execute("SELECT created_at FROM verified_payments WHERE id=%s", (vp["id"],))
    created = cursor.fetchone()["created_at"]
    period = f"{created.year:04d}-{created.month:02d}"

    rows = _parse_csv(
        svc.period_report_csv(sb_client, chapter_id=chapter_id, period=period, dataset="payments")
    )
    ids = {r["id"] for r in rows}
    assert vp["id"] in ids
    assert ovp["id"] not in ids


def test_report_invoices_dataset(sb_client, cursor, chapter_id, member_factory):
    """The invoices dataset reconciles to unpaid_invoices for the period."""
    m1 = member_factory()
    inv = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=m1, kind="dues",
        amount_cents=4200, description="dues", actor_id=m1,
    )
    cursor.execute("SELECT created_at FROM unpaid_invoices WHERE id=%s", (inv["id"],))
    created = cursor.fetchone()["created_at"]
    period = f"{created.year:04d}-{created.month:02d}"

    rows = _parse_csv(
        svc.period_report_csv(sb_client, chapter_id=chapter_id, period=period, dataset="invoices")
    )
    by_id = {r["id"]: r for r in rows}
    assert inv["id"] in by_id
    assert int(by_id[inv["id"]]["amount_cents"]) == 4200


def test_report_expenses_dataset(sb_client, cursor, chapter_id, member_factory):
    """The expenses dataset reconciles to chapter_expenses for the period."""
    m1 = member_factory()
    exp = exp_svc.create_expense(
        sb_client, chapter_id=chapter_id, category="supplies",
        amount_cents=1234, description="markers", actor_id=m1,
    )
    cursor.execute("SELECT created_at FROM chapter_expenses WHERE id=%s", (exp["id"],))
    created = cursor.fetchone()["created_at"]
    period = f"{created.year:04d}-{created.month:02d}"

    rows = _parse_csv(
        svc.period_report_csv(sb_client, chapter_id=chapter_id, period=period, dataset="expenses")
    )
    by_id = {r["id"]: r for r in rows}
    assert exp["id"] in by_id
    assert int(by_id[exp["id"]]["amount_cents"]) == 1234


def test_report_member_balances_dataset(sb_client, cursor, chapter_id, member_factory):
    """The member_balances dataset lists current member accounts for the chapter."""
    m1 = member_factory()
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=m1, kind="dues",
        amount_cents=7000, description=None, actor_id=m1,
    )
    # member_balances is a snapshot (not period-bound), but period is still required.
    rows = _parse_csv(
        svc.period_report_csv(
            sb_client, chapter_id=chapter_id, period="2026-06", dataset="member_balances"
        )
    )
    by_member = {r["member_id"]: r for r in rows}
    assert m1 in by_member
    assert int(by_member[m1]["outstanding_balance_cents"]) == 7000
    assert all(r["chapter_id"] == chapter_id for r in rows)


def test_report_ledger_dataset(sb_client, cursor, chapter_id, member_factory):
    """The ledger dataset reconciles to big_ledger for the period."""
    m1 = member_factory()
    inv = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=m1, kind="dues",
        amount_cents=9000, description=None, actor_id=m1,
    )
    cursor.execute(
        "SELECT created_at FROM big_ledger WHERE chapter_id=%s AND source_id=%s LIMIT 1",
        (chapter_id, inv["id"]),
    )
    created = cursor.fetchone()["created_at"]
    period = f"{created.year:04d}-{created.month:02d}"

    rows = _parse_csv(
        svc.period_report_csv(sb_client, chapter_id=chapter_id, period=period, dataset="ledger")
    )
    # The INVOICE_CREATED ledger entry for our invoice must be present.
    matching = [r for r in rows if r["source_id"] == inv["id"] and r["entry_type"] == "INVOICE_CREATED"]
    assert len(matching) == 1
    assert int(matching[0]["amount_cents"]) == 9000
    assert all(r["chapter_id"] == chapter_id for r in rows)


def test_report_rejects_unknown_dataset(sb_client, chapter_id):
    with pytest.raises(ValueError):
        svc.period_report_csv(sb_client, chapter_id=chapter_id, period="2026-06", dataset="bogus")


def test_report_rejects_bad_period(sb_client, chapter_id):
    with pytest.raises(ValueError):
        svc.period_report_csv(sb_client, chapter_id=chapter_id, period="2026-13", dataset="payments")
    with pytest.raises(ValueError):
        svc.period_report_csv(sb_client, chapter_id=chapter_id, period="not-a-period", dataset="payments")
