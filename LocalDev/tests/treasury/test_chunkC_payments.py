"""Chunk C — Payment Review & Receipts (Slices: double-verify, receipts).

The highest-stakes race in the system. Verification creates an immutable receipt,
a single PAYMENT_RECEIVED ledger entry, and exactly one verified_payment per
submission — provably so even under concurrency (UNIQUE(submission_id) + FOR UPDATE).

Every assertion is chapter-scoped; the append-only demo tables accumulate.
"""

from __future__ import annotations

import os
import threading
from datetime import timedelta
from pathlib import Path

import psycopg2
import pytest

from api.treasury.services import balance as bal_svc
from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _db_url() -> str | None:
    for k in ("TEST_DATABASE_URL", "SUPABASE_DB_URL"):
        v = os.environ.get(k)
        if v:
            return v
    env_path = _REPO_ROOT / ".env"
    if env_path.is_file():
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, val = line.partition("=")
            if name.strip() in ("TEST_DATABASE_URL", "SUPABASE_DB_URL") and val.strip():
                return val.strip()
    return None


# ── helpers ──────────────────────────────────────────────────────────────────
def _make_submission(sb, cursor, chapter_id, member_id, *, invoice_cents, claimed_cents):
    invoice = inv_svc.create_invoice(
        sb, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=invoice_cents, description=None, actor_id=member_id,
    )
    submission = inv_svc.submit_payment(
        sb, chapter_id=chapter_id, member_id=member_id, invoice_id=invoice["id"],
        claimed_amount_cents=claimed_cents, method="venmo", proof_ref="ref-1",
        actor_id=member_id,
    )
    return invoice, submission


def _verified_rows_for_submission(cursor, submission_id):
    cursor.execute(
        "SELECT * FROM verified_payments WHERE submission_id=%s", (submission_id,)
    )
    return cursor.fetchall()


def _payment_received_ledger(cursor, chapter_id, vp_id):
    cursor.execute(
        """SELECT * FROM big_ledger
           WHERE chapter_id=%s AND entry_type='PAYMENT_RECEIVED'
             AND source_table='verified_payments' AND source_id=%s""",
        (chapter_id, vp_id),
    )
    return cursor.fetchall()


# ── receipt: immutable & complete ────────────────────────────────────────────
def test_receipt_is_complete_after_verify(sb_client, cursor, chapter_id, member_id):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    vp = pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )

    cursor.execute(
        "SELECT * FROM receipts WHERE chapter_id=%s AND verified_payment_id=%s",
        (chapter_id, vp["id"]),
    )
    receipt = cursor.fetchone()
    assert receipt is not None
    assert str(receipt["verified_payment_id"]) == str(vp["id"])
    assert str(receipt["member_id"]) == str(member_id)
    assert receipt["amount_cents"] == 5000
    # F-029: coverage lives only in payment_allocations, not on the receipt/payment.
    assert receipt["invoice_id"] is None
    cursor.execute(
        "SELECT invoice_id, amount_cents FROM payment_allocations WHERE verified_payment_id=%s",
        (vp["id"],),
    )
    allocs = cursor.fetchall()
    assert [(str(a["invoice_id"]), a["amount_cents"]) for a in allocs] == [
        (str(submission["invoice_id"]), 5000)
    ]
    assert str(receipt["issued_by"]) == str(member_id)
    assert receipt["issued_at"] is not None


def test_receipt_is_immutable(sb_client, cursor, chapter_id, member_id):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    vp = pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    cursor.execute("SELECT id FROM receipts WHERE verified_payment_id=%s", (vp["id"],))
    receipt_id = cursor.fetchone()["id"]

    with pytest.raises(psycopg2.Error):
        cursor.execute("UPDATE receipts SET amount_cents=1 WHERE id=%s", (receipt_id,))
    with pytest.raises(psycopg2.Error):
        cursor.execute("DELETE FROM receipts WHERE id=%s", (receipt_id,))


# ── ledger + submission + invoice transitions ────────────────────────────────
def test_verify_writes_ledger_and_approves_submission(sb_client, cursor, chapter_id, member_id):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    vp = pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )

    ledger = _payment_received_ledger(cursor, chapter_id, vp["id"])
    assert len(ledger) == 1
    assert ledger[0]["amount_cents"] == 5000
    assert str(ledger[0]["member_id"]) == str(member_id)

    cursor.execute("SELECT status, reviewed_by FROM payment_submissions WHERE id=%s", (submission["id"],))
    row = cursor.fetchone()
    assert row["status"] == "approved"
    assert str(row["reviewed_by"]) == str(member_id)

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND target_id=%s AND action='VERIFY_PAYMENT'",
        (chapter_id, vp["id"]),
    )
    assert cursor.fetchone()["n"] == 1


def test_partial_payment_marks_invoice_partially_paid(sb_client, cursor, chapter_id, member_id):
    invoice, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=2000
    )
    pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice["id"],))
    assert cursor.fetchone()["status"] == "partially_paid"


def test_full_payment_marks_invoice_paid(sb_client, cursor, chapter_id, member_id):
    invoice, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice["id"],))
    assert cursor.fetchone()["status"] == "paid"


# ── member balance reflects the payment ──────────────────────────────────────
def test_member_balance_drops_by_payment(sb_client, cursor, chapter_id, member_id):
    invoice, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=2000
    )
    before = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert before["outstanding_balance_cents"] == 5000

    pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    after = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert after["outstanding_balance_cents"] == 3000


# ── idempotent verify (single-threaded) ──────────────────────────────────────
def test_verifying_twice_is_a_noop(sb_client, cursor, chapter_id, member_id):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    first = pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    second = pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    assert first["id"] == second["id"]
    assert len(_verified_rows_for_submission(cursor, submission["id"])) == 1
    # No internal flags leak to callers.
    assert "_created" not in first
    assert "_created" not in second


# ── exactly one approval notification on idempotent replay ───────────────────
def test_exactly_one_approval_notification(sb_client, cursor, chapter_id, member_id, monkeypatch):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    calls = {"n": 0}

    def _counter(**kwargs):
        calls["n"] += 1

    monkeypatch.setattr(pay_svc, "notify_payment_approved", _counter)

    pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    assert calls["n"] == 1


# ── concurrent double-verify → exactly one verified payment ──────────────────
def test_concurrent_double_verify_yields_exactly_one(cursor, chapter_id, member_id):
    db_url = _db_url()
    if not db_url:
        pytest.skip("no DB url")

    from api.platform.postgres import PostgresClient

    setup = PostgresClient(db_url)
    try:
        _, submission = _make_submission(
            setup, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
        )
    finally:
        setup.close()
    submission_id = submission["id"]

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def _attempt():
        client = PostgresClient(db_url)
        try:
            barrier.wait(timeout=10)
            client.rpc(
                "tr_verify_payment",
                {
                    "p_chapter_id": chapter_id,
                    "p_submission_id": submission_id,
                    "p_actor_id": member_id,
                },
            ).execute()
        except Exception as exc:  # noqa: BLE001 — a unique violation here is acceptable
            errors.append(exc)
        finally:
            client.close()

    t1 = threading.Thread(target=_attempt)
    t2 = threading.Thread(target=_attempt)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    rows = _verified_rows_for_submission(cursor, submission_id)
    assert len(rows) == 1, f"expected exactly one verified payment, got {len(rows)} (errors={errors})"


# ── reject has zero financial effect ─────────────────────────────────────────
def test_reject_has_no_financial_effect(sb_client, cursor, chapter_id, member_id):
    invoice, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    before = bal_svc.get_member_balance(sb_client, member_id=member_id)

    rejected = pay_svc.reject_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"],
        actor_id=member_id, reason="blurry proof",
    )
    assert rejected["status"] == "rejected"

    assert len(_verified_rows_for_submission(cursor, submission["id"])) == 0
    cursor.execute(
        """SELECT count(*) AS n FROM big_ledger
           WHERE chapter_id=%s AND entry_type='PAYMENT_RECEIVED' AND member_id=%s""",
        (chapter_id, member_id),
    )
    assert cursor.fetchone()["n"] == 0

    after = bal_svc.get_member_balance(sb_client, member_id=member_id)
    assert after["outstanding_balance_cents"] == before["outstanding_balance_cents"]

    cursor.execute(
        "SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND target_id=%s AND action='REJECT_PAYMENT'",
        (chapter_id, submission["id"]),
    )
    assert cursor.fetchone()["n"] == 1


def test_reject_is_idempotent(sb_client, cursor, chapter_id, member_id):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    pay_svc.reject_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    again = pay_svc.reject_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    assert again["status"] == "rejected"


def test_rejecting_an_approved_submission_raises(sb_client, cursor, chapter_id, member_id):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    with pytest.raises(Exception):
        pay_svc.reject_payment(
            sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
        )


def test_verifying_a_rejected_submission_raises(sb_client, cursor, chapter_id, member_id):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    pay_svc.reject_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    with pytest.raises(Exception):
        pay_svc.verify_payment(
            sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
        )


# ── get_receipt read ─────────────────────────────────────────────────────────
def test_get_receipt_returns_row_or_none(sb_client, cursor, chapter_id, member_id):
    _, submission = _make_submission(
        sb_client, cursor, chapter_id, member_id, invoice_cents=5000, claimed_cents=5000
    )
    vp = pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=member_id
    )
    cursor.execute("SELECT id FROM receipts WHERE verified_payment_id=%s", (vp["id"],))
    receipt_id = str(cursor.fetchone()["id"])

    got = pay_svc.get_receipt(sb_client, chapter_id=chapter_id, receipt_id=receipt_id)
    assert got is not None
    assert str(got["id"]) == receipt_id
    assert got["amount_cents"] == 5000

    import uuid as _uuid
    missing = pay_svc.get_receipt(sb_client, chapter_id=chapter_id, receipt_id=str(_uuid.uuid4()))
    assert missing is None


# ── orphan-sweep selection (read-only) ───────────────────────────────────────
def test_orphan_sweep_selects_only_old_rejected(sb_client, cursor, chapter_id, member_id):
    # Build two rejected submissions, one old, one recent. Insert raw so we control
    # reviewed_at precisely.
    cursor.execute(
        """INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
           VALUES (%s,%s,'dues',5000,'unpaid') RETURNING id""",
        (chapter_id, member_id),
    )
    invoice_id = cursor.fetchone()["id"]

    def _rejected_submission(reviewed_at_sql):
        cursor.execute(
            f"""INSERT INTO payment_submissions
                (chapter_id, member_id, invoice_id, claimed_amount_cents, method, proof_ref, status, reviewed_by, reviewed_at)
                VALUES (%s,%s,%s,5000,'venmo','ref','rejected',%s,{reviewed_at_sql})
                RETURNING id""",
            (chapter_id, member_id, invoice_id, member_id),
        )
        return str(cursor.fetchone()["id"])

    old_id = _rejected_submission("now() - interval '60 days'")
    recent_id = _rejected_submission("now() - interval '2 days'")

    # And a pending submission (must never be selected).
    cursor.execute(
        """INSERT INTO payment_submissions
            (chapter_id, member_id, invoice_id, claimed_amount_cents, method, proof_ref, status)
            VALUES (%s,%s,%s,5000,'venmo','ref','pending') RETURNING id""",
        (chapter_id, member_id, invoice_id),
    )
    pending_id = str(cursor.fetchone()["id"])

    selected = pay_svc.select_orphaned_proofs(sb_client, chapter_id=chapter_id, retention_days=30)
    ids = {str(r["id"]) for r in selected}
    assert old_id in ids
    assert recent_id not in ids
    assert pending_id not in ids

    # Nothing deleted.
    cursor.execute(
        "SELECT count(*) AS n FROM payment_submissions WHERE chapter_id=%s AND id IN (%s,%s,%s)",
        (chapter_id, old_id, recent_id, pending_id),
    )
    assert cursor.fetchone()["n"] == 3
