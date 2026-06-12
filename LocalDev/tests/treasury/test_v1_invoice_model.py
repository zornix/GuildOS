"""TREASURY V1 — invoice model: due_at, issued_by, 'manual' kind, line items,
and the V1 status presentation (open/void + overdue flag).

Follows the chunk test style: behavior through the service layer (real RPC path)
against the test DB; every assertion chapter-scoped.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

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


# ── create_invoice_v2: new columns ────────────────────────────────────────────
def test_create_invoice_v2_persists_due_at_issued_by_and_manual_kind(
    sb_client, cursor, chapter_id, member_id
):
    due = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    inv = svc.create_invoice_v2(
        sb_client,
        chapter_id=chapter_id,
        member_id=member_id,
        kind="manual",
        amount_cents=4200,
        description="Composite charge",
        actor_id=member_id,
        due_at=due.isoformat(),
    )
    assert inv["kind"] == "manual"
    assert inv["status"] == "unpaid"

    cursor.execute("SELECT due_at, issued_by FROM unpaid_invoices WHERE id = %s", (inv["id"],))
    row = cursor.fetchone()
    assert row["due_at"] is not None
    assert str(row["issued_by"]) == member_id  # issued_by populated from the actor


def test_create_invoice_v2_writes_ledger_and_audit(sb_client, cursor, chapter_id, member_id):
    inv = svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description="dues", actor_id=member_id,
    )
    ledger = _ledger(cursor, chapter_id, source_id=inv["id"])
    assert [r["entry_type"] for r in ledger] == ["INVOICE_CREATED"]
    assert ledger[0]["amount_cents"] == 5000
    audit = _audit(cursor, chapter_id, target_id=inv["id"], action="CREATE_INVOICE")
    assert len(audit) == 1


def test_create_invoice_v2_idempotent_on_replayed_key(sb_client, chapter_id, member_id):
    key = f"key-{uuid.uuid4()}"
    a = svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="manual",
        amount_cents=1000, description=None, actor_id=member_id, idempotency_key=key,
    )
    b = svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="manual",
        amount_cents=1000, description=None, actor_id=member_id, idempotency_key=key,
    )
    assert a["id"] == b["id"]


# ── line items ────────────────────────────────────────────────────────────────
def test_line_items_sum_must_equal_amount(sb_client, cursor, chapter_id, member_id):
    with pytest.raises(Exception):
        svc.create_invoice_v2(
            sb_client, chapter_id=chapter_id, member_id=member_id, kind="manual",
            amount_cents=5000, description=None, actor_id=member_id,
            line_items=[{"description": "only part", "amount_cents": 1000}],
        )
    # atomic: nothing persisted
    cursor.execute("SELECT count(*) AS n FROM unpaid_invoices WHERE chapter_id=%s", (chapter_id,))
    assert cursor.fetchone()["n"] == 0
    cursor.execute("SELECT count(*) AS n FROM invoice_line_items WHERE chapter_id=%s", (chapter_id,))
    assert cursor.fetchone()["n"] == 0


def test_line_items_persisted_when_sum_matches(sb_client, cursor, chapter_id, member_id):
    inv = svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="manual",
        amount_cents=3000, description="bundle", actor_id=member_id,
        line_items=[
            {"description": "setup fee", "amount_cents": 1000},
            {"description": "materials", "amount_cents": 2000},
        ],
    )
    cursor.execute(
        "SELECT description, amount_cents FROM invoice_line_items WHERE invoice_id=%s ORDER BY amount_cents",
        (inv["id"],),
    )
    rows = cursor.fetchall()
    assert [(r["description"], r["amount_cents"]) for r in rows] == [
        ("setup fee", 1000), ("materials", 2000),
    ]


def test_line_items_are_append_only(sb_client, cursor, chapter_id, member_id):
    inv = svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="manual",
        amount_cents=1000, description=None, actor_id=member_id,
        line_items=[{"description": "x", "amount_cents": 1000}],
    )
    cursor.execute("SELECT id FROM invoice_line_items WHERE invoice_id=%s", (inv["id"],))
    li_id = cursor.fetchone()["id"]
    with pytest.raises(Exception):
        cursor.execute("UPDATE invoice_line_items SET amount_cents = 1 WHERE id=%s", (li_id,))
    with pytest.raises(Exception):
        cursor.execute("DELETE FROM invoice_line_items WHERE id=%s", (li_id,))


# ── V1 presentation: open/void mapping + overdue flag ────────────────────────
def test_present_invoice_v1_maps_statuses_and_overdue():
    now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
    past_due = (now - timedelta(days=3)).isoformat()
    future_due = (now + timedelta(days=3)).isoformat()

    base = {"id": "i", "amount_cents": 100, "issued_by": "m", "kind": "dues"}

    unpaid = svc.present_invoice_v1({**base, "status": "unpaid", "due_at": past_due}, now=now)
    assert unpaid["status"] == "open"
    assert unpaid["raw_status"] == "unpaid"
    assert unpaid["overdue"] is True

    partial = svc.present_invoice_v1({**base, "status": "partially_paid", "due_at": future_due}, now=now)
    assert partial["status"] == "open"
    assert partial["overdue"] is False

    cancelled = svc.present_invoice_v1({**base, "status": "cancelled", "due_at": past_due}, now=now)
    assert cancelled["status"] == "void"
    assert cancelled["overdue"] is False

    paid = svc.present_invoice_v1({**base, "status": "paid", "due_at": past_due}, now=now)
    assert paid["status"] == "paid"
    assert paid["overdue"] is False

    no_due = svc.present_invoice_v1({**base, "status": "unpaid", "due_at": None}, now=now)
    assert no_due["overdue"] is False
    assert no_due["due_at"] is None
