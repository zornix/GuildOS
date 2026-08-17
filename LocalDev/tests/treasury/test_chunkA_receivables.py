"""Chunk A — Receivables & Fines (Slices 1, 2, 6, 13-bulk, §7.8).

Behavior is exercised through the service layer (the real RPC path) against the test
DB. recompute_member_balance is mocked: Chunk B fills BalanceEngine.recompute_member;
A only needs the call site to exist.
"""

from __future__ import annotations

import uuid

import pytest

from api.treasury.api.schemas import FineToInvoice
from api.treasury.core.money import Money
from api.treasury.services import invoices as svc


@pytest.fixture(autouse=True)
def _stub_recompute(monkeypatch):
    monkeypatch.setattr(svc, "recompute_member_balance", lambda sb, member_id: None)


def _ledger(cursor, chapter_id, **filt):
    sql = "SELECT * FROM big_ledger WHERE chapter_id = %s"
    params = [chapter_id]
    for k, v in filt.items():
        sql += f" AND {k} = %s"
        params.append(v)
    cursor.execute(sql, params)
    return cursor.fetchall()


def _audit(cursor, chapter_id, **filt):
    sql = "SELECT * FROM audit_logs WHERE chapter_id = %s"
    params = [chapter_id]
    for k, v in filt.items():
        sql += f" AND {k} = %s"
        params.append(v)
    cursor.execute(sql, params)
    return cursor.fetchall()


# ── Slice 1: create invoice ──────────────────────────────────────────────────
def test_create_invoice_persists_with_cents_and_unpaid(sb_client, cursor, chapter_id, member_id):
    inv = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description="Spring dues", actor_id=member_id,
    )
    assert inv["amount_cents"] == 5000
    assert inv["status"] == "unpaid"
    assert inv["kind"] == "dues"


def test_create_invoice_writes_one_ledger_and_one_audit(sb_client, cursor, chapter_id, member_id):
    inv = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="rent",
        amount_cents=12000, description=None, actor_id=member_id,
    )
    ledger = _ledger(cursor, chapter_id, source_id=inv["id"])
    assert len(ledger) == 1
    assert ledger[0]["entry_type"] == "INVOICE_CREATED"
    assert ledger[0]["source_table"] == "unpaid_invoices"
    assert ledger[0]["amount_cents"] == 12000

    audit = _audit(cursor, chapter_id, target_id=inv["id"], action="CREATE_INVOICE")
    assert len(audit) == 1


def test_create_invoice_idempotent_on_replayed_key(sb_client, chapter_id, member_id):
    key = f"key-{uuid.uuid4()}"
    a = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id, idempotency_key=key,
    )
    b = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id, idempotency_key=key,
    )
    assert a["id"] == b["id"]


# ── Slice 2: submit payment proof ────────────────────────────────────────────
def test_submit_payment_stores_pending_with_no_money(sb_client, cursor, chapter_id, member_id):
    inv = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    sub = svc.submit_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id, invoice_id=inv["id"],
        claimed_amount_cents=5000, method="venmo", proof_ref="img://x", actor_id=member_id,
    )
    assert sub["status"] == "pending"

    cursor.execute("SELECT count(*) AS n FROM verified_payments WHERE invoice_id = %s", (inv["id"],))
    assert cursor.fetchone()["n"] == 0
    # No ledger entry references the submission, and the invoice's only ledger row is INVOICE_CREATED.
    ledger = _ledger(cursor, chapter_id, source_id=inv["id"])
    assert [r["entry_type"] for r in ledger] == ["INVOICE_CREATED"]


def test_submit_payment_against_cancelled_invoice_is_rejected(sb_client, chapter_id, member_id):
    inv = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    svc.cancel_invoice(sb_client, chapter_id=chapter_id, invoice_id=inv["id"], actor_id=member_id)
    with pytest.raises(Exception):
        svc.submit_payment(
            sb_client, chapter_id=chapter_id, member_id=member_id, invoice_id=inv["id"],
            claimed_amount_cents=5000, method="cash", proof_ref=None, actor_id=member_id,
        )


def test_submit_payment_against_missing_invoice_is_rejected(sb_client, chapter_id, member_id):
    with pytest.raises(Exception):
        svc.submit_payment(
            sb_client, chapter_id=chapter_id, member_id=member_id, invoice_id=str(uuid.uuid4()),
            claimed_amount_cents=5000, method="zelle", proof_ref=None, actor_id=member_id,
        )


# ── Slice 6: cancel invoice (unpaid-only) ────────────────────────────────────
def test_cancel_unpaid_invoice_sets_status_and_negative_ledger(sb_client, cursor, chapter_id, member_id):
    inv = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    cancelled = svc.cancel_invoice(sb_client, chapter_id=chapter_id, invoice_id=inv["id"], actor_id=member_id)
    assert cancelled["status"] == "cancelled"

    ledger = _ledger(cursor, chapter_id, source_id=inv["id"], entry_type="CANCEL_INVOICE")
    assert len(ledger) == 1
    assert ledger[0]["amount_cents"] == -5000
    # Row still exists (no hard delete — invariant 1).
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id = %s", (inv["id"],))
    assert cursor.fetchone()["status"] == "cancelled"


def test_cancel_is_idempotent(sb_client, chapter_id, member_id):
    inv = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    svc.cancel_invoice(sb_client, chapter_id=chapter_id, invoice_id=inv["id"], actor_id=member_id)
    again = svc.cancel_invoice(sb_client, chapter_id=chapter_id, invoice_id=inv["id"], actor_id=member_id)
    assert again["status"] == "cancelled"


def test_cancel_paid_invoice_is_refused(sb_client, cursor, chapter_id, member_id):
    inv = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description=None, actor_id=member_id,
    )
    # Force the invoice to a non-unpaid status directly (Chunk C does this via verify).
    cursor.execute("UPDATE unpaid_invoices SET status='paid' WHERE id=%s", (inv["id"],))
    with pytest.raises(Exception):
        svc.cancel_invoice(sb_client, chapter_id=chapter_id, invoice_id=inv["id"], actor_id=member_id)


# ── Slice 13 (bulk only): atomic bulk invoice creation ───────────────────────
def test_bulk_create_invoices_is_atomic_and_emits_ledger_and_audit(sb_client, cursor, chapter_id, member_factory):
    m1, m2, m3 = member_factory(), member_factory(), member_factory()
    items = [
        {"member_id": m1, "kind": "dues", "amount_cents": 5000, "description": "d"},
        {"member_id": m2, "kind": "dues", "amount_cents": 5000, "description": "d"},
        {"member_id": m3, "kind": "dues", "amount_cents": 5000, "description": "d"},
    ]
    payload = svc.bulk_create_invoices(sb_client, chapter_id=chapter_id, invoices=items, actor_id=m1)
    assert payload["count"] == 3

    cursor.execute("SELECT count(*) AS n FROM unpaid_invoices WHERE chapter_id=%s", (chapter_id,))
    assert cursor.fetchone()["n"] == 3
    cursor.execute("SELECT count(*) AS n FROM big_ledger WHERE chapter_id=%s AND entry_type='INVOICE_CREATED'", (chapter_id,))
    assert cursor.fetchone()["n"] == 3
    cursor.execute("SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND action='CREATE_INVOICE'", (chapter_id,))
    assert cursor.fetchone()["n"] == 3


def test_bulk_create_invoices_forced_failure_leaves_zero_rows(sb_client, cursor, chapter_id, member_factory):
    m1, m2 = member_factory(), member_factory()
    items = [
        {"member_id": m1, "kind": "dues", "amount_cents": 5000, "description": "ok"},
        {"member_id": m2, "kind": "dues", "amount_cents": 0, "description": "bad"},  # violates amount>0
    ]
    with pytest.raises(Exception):
        svc.bulk_create_invoices(sb_client, chapter_id=chapter_id, invoices=items, actor_id=m1)

    cursor.execute("SELECT count(*) AS n FROM unpaid_invoices WHERE chapter_id=%s", (chapter_id,))
    assert cursor.fetchone()["n"] == 0
    cursor.execute("SELECT count(*) AS n FROM big_ledger WHERE chapter_id=%s", (chapter_id,))
    assert cursor.fetchone()["n"] == 0


# ── §7.8: fines integration + float boundary ─────────────────────────────────
def test_fine_amount_cents_validator_no_float_leakage():
    # 10.10 in binary float is 10.0999999...; the validator must yield exactly 1010 cents.
    dto = FineToInvoice(fine_amount=10.10)
    assert dto.fine_amount_cents == 1010
    assert isinstance(dto.fine_amount_cents, int)
    assert FineToInvoice(fine_amount=0.1 + 0.2).fine_amount_cents == 30
    assert FineToInvoice(fine_amount=25).fine_amount_cents == 2500


def test_legacy_fines_table_is_frozen(cursor, chapter_id, member_id):
    with pytest.raises(Exception):
        cursor.execute(
            "INSERT INTO fines (member_id, chapter_id, amount, reason, status) VALUES (%s,%s,%s,%s,%s)",
            (member_id, chapter_id, 10, "x", "unpaid"),
        )


async def test_fine_processor_creates_fine_invoices_and_dedups(sb_client, cursor, chapter_id, member_factory, monkeypatch):
    import api.treasury.services.fine_processor as fp

    monkeypatch.setattr(fp, "get_db", lambda: sb_client)

    m1, m2 = member_factory(), member_factory()
    cursor.execute(
        """INSERT INTO events (chapter_id, title, description, date, time, location, required, fine_amount)
           VALUES (%s,'Chapter Meeting','',CURRENT_DATE,'18:00','Hall',true,15.50) RETURNING id""",
        (chapter_id,),
    )
    event_id = str(cursor.fetchone()["id"])

    created = await fp.process_event_fines(event_id)
    assert len(created) == 2
    for inv in created:
        assert inv["kind"] == "fine"
        assert inv["amount_cents"] == 1550  # 15.50 → 1550, no float drift
        assert inv["status"] == "unpaid"

    # Running again must not double-fine (dedup on source_event_id).
    again = await fp.process_event_fines(event_id)
    assert again == []
    cursor.execute(
        "SELECT count(*) AS n FROM unpaid_invoices WHERE source_event_id=%s AND kind='fine'", (event_id,)
    )
    assert cursor.fetchone()["n"] == 2
