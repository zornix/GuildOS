"""Chunk G — Rebuild & Hardening (Slices 11, 12; §3 invariants; §5 RebuildEngine).

The RebuildEngine reconstructs the ledger + balances from the OPERATIONAL tables
(a shadow), diffs the shadow against the live `big_ledger` and the live
`member_finance_accounts` cache, and returns a drift report. It may overwrite ONLY
the balance cache; it must NEVER DELETE or UPDATE `big_ledger`.

Hardening covers the durable notification outbox (exactly-once / dry_run) and an
automated sweep of the load-bearing append-only / independence invariants.

Every assertion is chapter-scoped; the append-only demo tables accumulate.
"""

from __future__ import annotations

import uuid

import psycopg2
import pytest

from api.treasury.core.balance import BalanceEngine
from api.treasury.core.rebuild import RebuildEngine
from api.treasury.services import adjustments as adj_svc
from api.treasury.services import expenses as exp_svc
from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc
from api.treasury.services import refunds as ref_svc


# ── setup helpers ─────────────────────────────────────────────────────────────
def _full_lifecycle(sb, chapter_id, member_id, member_factory):
    """Exercise one money-move of every kind so the ledger has all entry types.

    Returns a dict of the created rows for downstream assertions.
    """
    # Invoice the member, then have them overpay so a credit (refundable) exists.
    invoice = inv_svc.create_invoice(
        sb, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    submission = inv_svc.submit_payment(
        sb, chapter_id=chapter_id, member_id=member_id, invoice_id=invoice["id"],
        claimed_amount_cents=7000, method="venmo", proof_ref="ref-1", actor_id=member_id,
    )
    vp = pay_svc.verify_payment(
        sb, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    # A second invoice that gets cancelled → INVOICE_CREATED + CANCEL_INVOICE.
    cancelled = inv_svc.create_invoice(
        sb, chapter_id=chapter_id, member_id=member_id, kind="fine",
        amount_cents=1500, description="late", actor_id=member_id,
    )
    inv_svc.cancel_invoice(
        sb, chapter_id=chapter_id, invoice_id=cancelled["id"], actor_id=member_id
    )
    # An expense (chapter money out).
    expense = exp_svc.create_expense(
        sb, chapter_id=chapter_id, category="supplies", amount_cents=2000,
        description="banner", actor_id=member_id,
    )
    # A member adjustment + a chapter adjustment (both active, under threshold).
    member_adj = adj_svc.create_adjustment(
        sb, chapter_id=chapter_id, member_id=member_id, kind="manual_correction",
        delta_cents=-500, reason="goodwill", officer_id=member_id,
    )
    chapter_adj = adj_svc.create_adjustment(
        sb, chapter_id=chapter_id, member_id=None, kind="manual_correction",
        delta_cents=3000, reason="found cash", officer_id=member_id,
    )
    # A refund against the overpayment.
    refund = ref_svc.issue_refund(
        sb, chapter_id=chapter_id, verified_payment_id=vp["id"], amount_cents=2000,
        reason="return overpayment", officer_id=member_id,
    )
    return {
        "invoice": invoice, "vp": vp, "cancelled": cancelled, "expense": expense,
        "member_adj": member_adj, "chapter_adj": chapter_adj, "refund": refund,
    }


def _live_active_ledger(cursor, chapter_id):
    cursor.execute(
        "SELECT entry_type, amount_cents, member_id FROM big_ledger "
        "WHERE chapter_id=%s AND status='active'",
        (chapter_id,),
    )
    return cursor.fetchall()


# ── §5 RebuildEngine: parity on a clean chapter ──────────────────────────────
def test_rebuild_is_clean_after_full_lifecycle(sb_client, cursor, chapter_id, member_id, member_factory):
    _full_lifecycle(sb_client, chapter_id, member_id, member_factory)

    report = RebuildEngine(sb_client).rebuild(chapter_id)

    assert report.ledger_drift == []
    assert report.balance_drift == []
    assert report.is_clean


def test_reconstructed_ledger_multiset_equals_live(sb_client, cursor, chapter_id, member_id, member_factory):
    _full_lifecycle(sb_client, chapter_id, member_id, member_factory)

    report = RebuildEngine(sb_client).rebuild(chapter_id)

    # The reconstructed entry-type histogram must equal the live active ledger's.
    from collections import Counter

    recon = Counter(e["entry_type"] for e in report.reconstructed_ledger)
    live = Counter(r["entry_type"] for r in _live_active_ledger(cursor, chapter_id))
    assert recon == live
    # Every entry type the lifecycle produces is represented.
    assert recon["INVOICE_CREATED"] == 2          # dues + fine
    assert recon["CANCEL_INVOICE"] == 1
    assert recon["PAYMENT_RECEIVED"] == 1
    assert recon["EXPENSE_APPROVED"] == 1
    assert recon["ADJUSTMENT_CREATED"] == 2       # member + chapter
    assert recon["REFUND_ISSUED"] == 1


# ── §5 RebuildEngine: balance-cache drift ────────────────────────────────────
def test_rebuild_flags_stale_balance_cache(sb_client, cursor, chapter_id, member_id):
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    # Corrupt the cache behind the engine's back.
    cursor.execute(
        "UPDATE member_finance_accounts SET outstanding_balance_cents=999999, "
        "current_balance_cents=999999 WHERE chapter_id=%s AND member_id=%s",
        (chapter_id, member_id),
    )

    report = RebuildEngine(sb_client).rebuild(chapter_id)

    assert not report.is_clean
    drifted_members = {d["member_id"] for d in report.balance_drift}
    assert str(member_id) in {str(m) for m in drifted_members}


def test_rebuild_repairs_only_the_balance_cache(sb_client, cursor, chapter_id, member_id):
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    cursor.execute(
        "UPDATE member_finance_accounts SET outstanding_balance_cents=999999 "
        "WHERE chapter_id=%s AND member_id=%s",
        (chapter_id, member_id),
    )

    report = RebuildEngine(sb_client).rebuild(chapter_id, apply_repairs=True)
    assert report.repaired

    # Cache is now correct, and a follow-up rebuild is clean.
    cursor.execute(
        "SELECT outstanding_balance_cents FROM member_finance_accounts "
        "WHERE chapter_id=%s AND member_id=%s",
        (chapter_id, member_id),
    )
    assert cursor.fetchone()["outstanding_balance_cents"] == 5000
    assert RebuildEngine(sb_client).rebuild(chapter_id).is_clean


# ── §3.1 invariant: rebuild never mutates the append-only ledger ─────────────
def test_rebuild_issues_no_delete_or_update_on_big_ledger(sb_client, cursor, chapter_id, member_id, member_factory):
    _full_lifecycle(sb_client, chapter_id, member_id, member_factory)

    def snapshot():
        cursor.execute(
            "SELECT id, entry_type, amount_cents, status, created_at, member_id, "
            "source_table, source_id FROM big_ledger WHERE chapter_id=%s ORDER BY id",
            (chapter_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    before = snapshot()
    # Force the repair path (the only path allowed to write anything).
    RebuildEngine(sb_client).rebuild(chapter_id, apply_repairs=True)
    after = snapshot()

    assert before == after            # no row changed, none vanished, none added
    assert len(before) == len(after)


# ── §5 determinism ───────────────────────────────────────────────────────────
def test_rebuild_is_deterministic(sb_client, cursor, chapter_id, member_id, member_factory):
    _full_lifecycle(sb_client, chapter_id, member_id, member_factory)
    eng = RebuildEngine(sb_client)
    first = eng.rebuild(chapter_id)
    second = eng.rebuild(chapter_id)
    assert first.reconstructed_ledger == second.reconstructed_ledger
    assert first.ledger_drift == second.ledger_drift
    assert first.balance_drift == second.balance_drift


# ── deviation #12: a pending over-threshold adjustment has NO ledger entry ────
def test_rebuild_excludes_pending_adjustment_then_includes_after_signoff(
    sb_client, cursor, chapter_id, member_id, member_factory
):
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=200000, description=None, actor_id=member_id,
    )
    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues_forgiveness",
        delta_cents=-100000, reason="large waive", officer_id=member_id, threshold_cents=50000,
    )
    assert adj["status"] == "pending"

    # Pending → no ADJUSTMENT_CREATED reconstructed, and the rebuild is clean
    # (live ledger also has none).
    report = RebuildEngine(sb_client).rebuild(chapter_id)
    assert not any(
        e["entry_type"] == "ADJUSTMENT_CREATED" and str(e.get("source_id")) == str(adj["id"])
        for e in report.reconstructed_ledger
    )
    assert report.is_clean

    # Activate via a second officer → now exactly one ADJUSTMENT_CREATED, still clean.
    approver = member_factory()
    adj_svc.approve_adjustment(
        sb_client, chapter_id=chapter_id, adjustment_id=adj["id"], approver_id=approver
    )
    report2 = RebuildEngine(sb_client).rebuild(chapter_id)
    assert sum(
        1 for e in report2.reconstructed_ledger
        if e["entry_type"] == "ADJUSTMENT_CREATED" and str(e.get("source_id")) == str(adj["id"])
    ) == 1
    assert report2.is_clean


# ── injected inconsistency is flagged ────────────────────────────────────────
def test_rebuild_flags_a_ledger_entry_with_no_operational_backing(
    sb_client, cursor, chapter_id, member_id
):
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    # Smuggle a phantom ledger entry that no operational row justifies.
    cursor.execute(
        "INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, "
        "source_table, source_id, status) "
        "VALUES (%s,'ADJUSTMENT_CREATED',777,%s,'finance_adjustments',%s,'active')",
        (chapter_id, member_id, str(uuid.uuid4())),
    )

    report = RebuildEngine(sb_client).rebuild(chapter_id)
    assert any(d["kind"] == "extra" and d["amount_cents"] == 777 for d in report.ledger_drift)
    assert not report.is_clean


# ── F-058: PAYMENT_RECEIVED is matched to its source ─────────────────────────
def test_missing_and_stray_payment_rows_do_not_cancel_out(sb_client, cursor, chapter_id, member_id):
    vps = []
    for _ in range(2):
        sub = pay_svc.submit_balance_payment(
            sb_client, chapter_id=chapter_id, member_id=member_id,
            claimed_amount_cents=2500, method="venmo", proof_ref=None,
        )
        vps.append(pay_svc.verify_payment_v2(
            sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
        ))
    # Hole: payment A's ledger row invalidated. Orphan: a same-amount row pointing nowhere.
    cursor.execute(
        "UPDATE big_ledger SET status='invalidated' WHERE chapter_id=%s AND source_id=%s",
        (chapter_id, vps[0]["id"]),
    )
    cursor.execute(
        "INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, "
        "source_table, source_id, status) "
        "VALUES (%s,'PAYMENT_RECEIVED',2500,%s,'verified_payments',%s,'active')",
        (chapter_id, member_id, str(uuid.uuid4())),
    )

    report = RebuildEngine(sb_client).rebuild(chapter_id)

    assert not report.is_clean
    assert {d["kind"] for d in report.ledger_drift} == {"missing", "extra"}


def test_migrated_0012_payment_row_still_matches_its_payment(sb_client, cursor, chapter_id, member_id):
    """0012 wrote PAYMENT_RECEIVED with source unpaid_invoices/<invoice id>; 0165
    moved the payment's coverage into an allocation. Rebuild must treat them as one."""
    from tests.treasury.test_single_coverage import _legacy_paid_invoice, _run_0165_data

    invoice_id, _vp = _legacy_paid_invoice(cursor, chapter_id, member_id, 2500)
    for entry_type in ("INVOICE_CREATED", "PAYMENT_RECEIVED"):
        cursor.execute(
            "INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, "
            "source_table, source_id, status) "
            "VALUES (%s,%s,2500,%s,'unpaid_invoices',%s,'active')",
            (chapter_id, entry_type, member_id, invoice_id),
        )
    _run_0165_data(cursor)
    BalanceEngine(sb_client).recompute_member(member_id)

    report = RebuildEngine(sb_client).rebuild(chapter_id)

    assert report.ledger_drift == []
    assert report.is_clean


# ── Slice 12 hardening: durable notification outbox ──────────────────────────
def test_notification_persists_pending_row_in_dry_run(sb_client, cursor, chapter_id, member_id):
    from api.treasury.notifications import notify_payment_approved

    submission_id = str(uuid.uuid4())
    row = notify_payment_approved(
        chapter_id=chapter_id, member_id=member_id, submission_id=submission_id, sb=sb_client
    )
    assert row is not None
    assert row["status"] == "pending"
    assert row["delivery_mode"] == "dry_run"

    cursor.execute(
        "SELECT count(*) AS n FROM message_outbox WHERE dedup_key=%s",
        (f"PAYMENT_APPROVED:{submission_id}",),
    )
    assert cursor.fetchone()["n"] == 1


def test_notification_is_exactly_once_on_retry(sb_client, cursor, chapter_id, member_id):
    from api.treasury.notifications import notify_refund_issued

    refund_id = str(uuid.uuid4())
    first = notify_refund_issued(
        chapter_id=chapter_id, member_id=member_id, refund_id=refund_id, sb=sb_client
    )
    second = notify_refund_issued(
        chapter_id=chapter_id, member_id=member_id, refund_id=refund_id, sb=sb_client
    )
    assert first is not None
    assert second is None  # dedup short-circuit → no second row

    cursor.execute(
        "SELECT count(*) AS n FROM message_outbox WHERE dedup_key=%s",
        (f"REFUND_ISSUED:{refund_id}",),
    )
    assert cursor.fetchone()["n"] == 1


# ── Slice 14: invoice-issued notification is wired and exactly-once ──────────
def test_invoice_creation_enqueues_one_invoice_issued_notification(sb_client, cursor, chapter_id, member_id):
    inv = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    cursor.execute(
        "SELECT count(*) AS n, max(event_type) AS et FROM message_outbox WHERE dedup_key=%s",
        (f"INVOICE_ISSUED:{inv['id']}",),
    )
    row = cursor.fetchone()
    assert row["n"] == 1
    assert row["et"] == "INVOICE_ISSUED"


def test_invoice_issued_notification_is_exactly_once_on_idempotent_replay(sb_client, cursor, chapter_id, member_id):
    key = "inv-issue-key-1"
    a = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id, idempotency_key=key,
    )
    b = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id, idempotency_key=key,
    )
    assert a["id"] == b["id"]  # idempotent replay returns the same invoice
    cursor.execute(
        "SELECT count(*) AS n FROM message_outbox WHERE dedup_key=%s",
        (f"INVOICE_ISSUED:{a['id']}",),
    )
    assert cursor.fetchone()["n"] == 1


# ── §3 invariant sweep (load-bearing append-only / independence rules) ────────
def test_invariant_big_ledger_is_delete_blocked(sb_client, cursor, chapter_id, member_id):
    inv = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    with pytest.raises(psycopg2.Error):
        cursor.execute(
            "DELETE FROM big_ledger WHERE chapter_id=%s AND source_id=%s",
            (chapter_id, inv["id"]),
        )


def test_invariant_audit_logs_is_delete_blocked(sb_client, cursor, chapter_id, member_id):
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    with pytest.raises(psycopg2.Error):
        cursor.execute("DELETE FROM audit_logs WHERE chapter_id=%s", (chapter_id,))


def test_invariant_member_balance_is_independent_of_the_ledger(sb_client, cursor, chapter_id, member_id):
    """Invariant 3 — balances are computed from operational tables, never the ledger.

    A phantom PAYMENT_RECEIVED in the ledger must NOT move the member's balance.
    """
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    before = BalanceEngine(sb_client).member_outstanding(member_id).cents
    cursor.execute(
        "INSERT INTO big_ledger (chapter_id, entry_type, amount_cents, member_id, "
        "source_table, source_id, status) "
        "VALUES (%s,'PAYMENT_RECEIVED',5000,%s,'verified_payments',%s,'active')",
        (chapter_id, member_id, str(uuid.uuid4())),
    )
    after = BalanceEngine(sb_client).member_outstanding(member_id).cents
    assert after == before == 5000


# ── endpoint gating: POST /rebuild requires treasury:rebuild:run ────────────
# 0147: the gate is a catalog permission carried by a role, not a grant row.
async def test_rebuild_requires_rebuild_run_permission(sb_client, cursor, chapter_id, member_id, monkeypatch):
    from fastapi import HTTPException

    import api.rbac.services.permissions as rbac_permissions
    from api.rbac.auth import require_permission
    from api.treasury.api import rebuild

    monkeypatch.setattr(rbac_permissions, "get_db", lambda: sb_client)
    dep = require_permission(rebuild.REBUILD_RUN)
    user = {"id": member_id, "chapter_id": chapter_id, "role": "member"}

    with pytest.raises(HTTPException) as exc:
        await dep(user=user)
    assert exc.value.status_code == 403

    cursor.execute(
        "INSERT INTO member_roles (chapter_id, member_id, role_key) VALUES (%s,%s,'treasurer') "
        "ON CONFLICT DO NOTHING",
        (chapter_id, member_id),
    )
    assert await dep(user=user) == user
