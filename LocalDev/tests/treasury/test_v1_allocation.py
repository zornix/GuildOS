"""TREASURY V1 — verification + allocation (decision #2).

tr_verify_payment_v2 verifies a submission (invoice-targeted OR balance-level)
and allocates the amount across the member's open invoices OLDEST-FIRST via
append-only payment_allocations rows; leftover stays member credit.
tr_reallocate_payment is the treasurer override: reversal rows + new rows.
"""

from __future__ import annotations

import uuid

import pytest

from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401


@pytest.fixture(autouse=True)
def _stub_invoice_recompute(monkeypatch):
    monkeypatch.setattr(inv_svc, "recompute_member_balance", lambda sb, member_id: None)


def _invoice(sb_client, chapter_id, member_id, amount):
    return inv_svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=amount, description=None, actor_id=member_id,
    )


def _balance_submission(sb_client, chapter_id, member_id, amount, method="venmo"):
    return pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=amount, method=method, proof_ref=None,
    )


def _invoice_status(cursor, invoice_id):
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice_id,))
    return cursor.fetchone()["status"]


def _allocations(cursor, chapter_id, **filt):
    sql = "SELECT * FROM payment_allocations WHERE chapter_id=%s"
    params = [chapter_id]
    for k, v in filt.items():
        sql += f" AND {k} = %s"
        params.append(v)
    sql += " ORDER BY created_at, id"
    cursor.execute(sql, params)
    return cursor.fetchall()


# ── verify v2: oldest-first allocation ────────────────────────────────────────
def test_verify_v2_allocates_oldest_first_with_partial_coverage(
    sb_client, cursor, chapter_id, member_id
):
    inv_a = _invoice(sb_client, chapter_id, member_id, 5000)  # oldest
    inv_b = _invoice(sb_client, chapter_id, member_id, 3000)
    sub = _balance_submission(sb_client, chapter_id, member_id, 6000)

    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    assert vp["amount_cents"] == 6000

    assert _invoice_status(cursor, inv_a["id"]) == "paid"
    assert _invoice_status(cursor, inv_b["id"]) == "partially_paid"

    allocs = _allocations(cursor, chapter_id, verified_payment_id=vp["id"])
    by_invoice = {str(a["invoice_id"]): a["amount_cents"] for a in allocs}
    assert by_invoice == {inv_a["id"]: 5000, inv_b["id"]: 1000}

    # PAYMENT_RECEIVED ledger + receipt exist (mirroring 0031)
    cursor.execute(
        "SELECT count(*) AS n FROM big_ledger WHERE chapter_id=%s AND entry_type='PAYMENT_RECEIVED' AND source_id=%s",
        (chapter_id, vp["id"]),
    )
    assert cursor.fetchone()["n"] == 1
    cursor.execute(
        "SELECT count(*) AS n FROM receipts WHERE verified_payment_id=%s", (vp["id"],)
    )
    assert cursor.fetchone()["n"] == 1


def test_verify_v2_leftover_stays_member_credit(sb_client, cursor, chapter_id, member_id):
    inv_a = _invoice(sb_client, chapter_id, member_id, 2000)
    sub = _balance_submission(sb_client, chapter_id, member_id, 5000)

    pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    assert _invoice_status(cursor, inv_a["id"]) == "paid"

    # balance engine: owed 2000, paid 5000 → current −3000 (credit)
    cursor.execute(
        "SELECT current_balance_cents FROM member_finance_accounts WHERE member_id=%s",
        (member_id,),
    )
    assert cursor.fetchone()["current_balance_cents"] == -3000


def test_verify_v2_works_for_invoice_targeted_submissions(
    sb_client, cursor, chapter_id, member_id
):
    inv_a = _invoice(sb_client, chapter_id, member_id, 1000)  # oldest
    inv_b = _invoice(sb_client, chapter_id, member_id, 4000)
    # invoice-targeted submission against inv_b
    sub = pay_svc_submit_legacy(sb_client, chapter_id, member_id, inv_b["id"], 4000)

    pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    # F-032 / D7: the picked invoice is paid first; the older one is untouched
    assert _invoice_status(cursor, inv_b["id"]) == "paid"
    assert _invoice_status(cursor, inv_a["id"]) == "unpaid"


def test_targeted_surplus_flows_oldest_first(sb_client, cursor, chapter_id, member_id):
    inv_a = _invoice(sb_client, chapter_id, member_id, 3000)  # oldest
    inv_b = _invoice(sb_client, chapter_id, member_id, 4000)
    sub = pay_svc_submit_legacy(sb_client, chapter_id, member_id, inv_b["id"], 5000)

    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    assert _invoice_status(cursor, inv_b["id"]) == "paid"
    assert _invoice_status(cursor, inv_a["id"]) == "partially_paid"
    allocs = _allocations(cursor, chapter_id, verified_payment_id=vp["id"])
    assert {str(a["invoice_id"]): a["amount_cents"] for a in allocs} == {
        inv_b["id"]: 4000, inv_a["id"]: 1000,
    }


def test_target_already_closed_falls_back_to_oldest_first(
    sb_client, cursor, chapter_id, member_id
):
    inv_a = _invoice(sb_client, chapter_id, member_id, 3000)  # oldest
    inv_b = _invoice(sb_client, chapter_id, member_id, 2000)
    sub = pay_svc_submit_legacy(sb_client, chapter_id, member_id, inv_b["id"], 2000)
    cursor.execute(
        "SELECT tr_void_invoice(%s, %s, %s, %s)",
        (chapter_id, inv_b["id"], member_id, "issued by mistake"),
    )

    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    assert _invoice_status(cursor, inv_b["id"]) == "cancelled"
    assert _invoice_status(cursor, inv_a["id"]) == "partially_paid"
    allocs = _allocations(cursor, chapter_id, verified_payment_id=vp["id"])
    assert {str(a["invoice_id"]): a["amount_cents"] for a in allocs} == {inv_a["id"]: 2000}


def pay_svc_submit_legacy(sb_client, chapter_id, member_id, invoice_id, amount):
    from api.treasury.services.invoices import submit_payment

    return submit_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id, invoice_id=invoice_id,
        claimed_amount_cents=amount, method="venmo", proof_ref=None, actor_id=member_id,
    )


def test_verify_v2_idempotent_replay(sb_client, cursor, chapter_id, member_id):
    _invoice(sb_client, chapter_id, member_id, 1000)
    sub = _balance_submission(sb_client, chapter_id, member_id, 1000)
    key = f"v2-{uuid.uuid4()}"
    a = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"],
        actor_id=member_id, idempotency_key=key,
    )
    b = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"],
        actor_id=member_id, idempotency_key=key,
    )
    assert a["id"] == b["id"]
    cursor.execute(
        "SELECT count(*) AS n FROM verified_payments WHERE submission_id=%s", (sub["id"],)
    )
    assert cursor.fetchone()["n"] == 1


# ── reallocation: append-only treasurer override ──────────────────────────────
def test_reallocate_appends_reversals_and_flips_statuses(
    sb_client, cursor, chapter_id, member_id
):
    inv_a = _invoice(sb_client, chapter_id, member_id, 3000)
    inv_b = _invoice(sb_client, chapter_id, member_id, 3000)
    sub = _balance_submission(sb_client, chapter_id, member_id, 3000)
    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    assert _invoice_status(cursor, inv_a["id"]) == "paid"
    assert _invoice_status(cursor, inv_b["id"]) == "unpaid"
    before = _allocations(cursor, chapter_id, verified_payment_id=vp["id"])
    assert len(before) == 1

    pay_svc.reallocate_payment(
        sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
        allocations=[{"invoice_id": inv_b["id"], "amount_cents": 3000}],
        actor_id=member_id, reason="member asked to cover the fine first",
    )

    after = _allocations(cursor, chapter_id, verified_payment_id=vp["id"])
    # append-only: original row + reversal row + new row
    assert len(after) == 3
    originals = [a for a in after if a["reverses_allocation_id"] is None]
    reversals = [a for a in after if a["reverses_allocation_id"] is not None]
    assert len(reversals) == 1
    assert str(reversals[0]["reverses_allocation_id"]) == str(before[0]["id"])
    assert reversals[0]["amount_cents"] == 3000  # positive amount, reversal by reference
    assert {str(a["invoice_id"]) for a in originals} == {inv_a["id"], inv_b["id"]}

    # statuses flipped
    assert _invoice_status(cursor, inv_a["id"]) == "unpaid"
    assert _invoice_status(cursor, inv_b["id"]) == "paid"

    # audit logged with the reason
    cursor.execute(
        "SELECT metadata FROM audit_logs WHERE chapter_id=%s AND target_id=%s ORDER BY created_at DESC",
        (chapter_id, vp["id"]),
    )
    metas = [r["metadata"] for r in cursor.fetchall()]
    assert any(m.get("reason") == "member asked to cover the fine first" for m in metas)


def test_reallocate_requires_reason(sb_client, cursor, chapter_id, member_id):
    inv_a = _invoice(sb_client, chapter_id, member_id, 1000)
    sub = _balance_submission(sb_client, chapter_id, member_id, 1000)
    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    with pytest.raises(Exception):
        pay_svc.reallocate_payment(
            sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
            allocations=[{"invoice_id": inv_a["id"], "amount_cents": 1000}],
            actor_id=member_id, reason="",
        )


def test_reallocate_cannot_exceed_verified_amount(sb_client, cursor, chapter_id, member_id):
    inv_a = _invoice(sb_client, chapter_id, member_id, 9000)
    sub = _balance_submission(sb_client, chapter_id, member_id, 1000)
    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    with pytest.raises(Exception):
        pay_svc.reallocate_payment(
            sb_client, chapter_id=chapter_id, verified_payment_id=vp["id"],
            allocations=[{"invoice_id": inv_a["id"], "amount_cents": 2000}],
            actor_id=member_id, reason="too much",
        )


def test_allocation_rows_block_update_and_delete(sb_client, cursor, chapter_id, member_id):
    _invoice(sb_client, chapter_id, member_id, 1000)
    sub = _balance_submission(sb_client, chapter_id, member_id, 1000)
    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=member_id,
    )
    rows = _allocations(cursor, chapter_id, verified_payment_id=vp["id"])
    with pytest.raises(Exception):
        cursor.execute("UPDATE payment_allocations SET amount_cents=1 WHERE id=%s", (rows[0]["id"],))
    with pytest.raises(Exception):
        cursor.execute("DELETE FROM payment_allocations WHERE id=%s", (rows[0]["id"],))


# ── endpoints: verify-v1 / reject-v1 / reallocate / allocations ──────────────
def test_verify_v1_endpoint_gating(api, sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    plain = member_factory()
    treasurer = member_factory()
    finance = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    assign_role(cursor, chapter_id, finance, "finance_board")

    _invoice(sb_client, chapter_id, member, 1000)
    sub1 = _balance_submission(sb_client, chapter_id, member, 500)
    sub2 = _balance_submission(sb_client, chapter_id, member, 500, method="zelle")

    # A plain member lacks treasury:payment:verify → 403. (Not a generic officer:
    # 0147 grants the officer role that key, preserving pre-one-gate access.)
    resp = api(make_user(plain, chapter_id)).post(
        f"/api/treasury/payments/submissions/{sub1['id']}/verify-v1",
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 403

    # treasurer verifies
    resp = api(make_user(treasurer, chapter_id)).post(
        f"/api/treasury/payments/submissions/{sub1['id']}/verify-v1",
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text

    # finance_board verifies too (decision #2)
    resp = api(make_user(finance, chapter_id)).post(
        f"/api/treasury/payments/submissions/{sub2['id']}/verify-v1",
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text


def test_reject_v1_requires_nonempty_reason(api, sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    sub = _balance_submission(sb_client, chapter_id, member, 500)

    client = api(make_user(treasurer, chapter_id))
    resp = client.post(
        f"/api/treasury/payments/submissions/{sub['id']}/reject-v1",
        json={"reason": "  "},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 422

    resp = client.post(
        f"/api/treasury/payments/submissions/{sub['id']}/reject-v1",
        json={"reason": "no matching Venmo transaction"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text
    cursor.execute("SELECT status FROM payment_submissions WHERE id=%s", (sub["id"],))
    assert cursor.fetchone()["status"] == "rejected"
    cursor.execute(
        "SELECT metadata FROM audit_logs WHERE chapter_id=%s AND action='REJECT_PAYMENT' AND target_id=%s",
        (chapter_id, sub["id"]),
    )
    metas = [r["metadata"] for r in cursor.fetchall()]
    assert any(m.get("reason") == "no matching Venmo transaction" for m in metas)


def test_reallocate_endpoint_treasurer_only(api, sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    treasurer = member_factory()
    finance = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    assign_role(cursor, chapter_id, finance, "finance_board")

    inv_a = _invoice(sb_client, chapter_id, member, 1000)
    inv_b = _invoice(sb_client, chapter_id, member, 1000)
    sub = _balance_submission(sb_client, chapter_id, member, 1000)
    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=treasurer,
    )

    body = {
        "allocations": [{"invoice_id": inv_b["id"], "amount_cents": 1000}],
        "reason": "override",
    }
    # finance_board lacks treasury:invoice:void → 403 (treasurer-only override)
    resp = api(make_user(finance, chapter_id)).post(
        f"/api/treasury/payments/{vp['id']}/reallocate",
        json=body, headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 403

    resp = api(make_user(treasurer, chapter_id)).post(
        f"/api/treasury/payments/{vp['id']}/reallocate",
        json=body, headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text

    # transparency read
    resp = api(make_user(treasurer, chapter_id)).get(
        f"/api/treasury/payments/{vp['id']}/allocations",
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3  # original + reversal + new


def test_reallocate_endpoint_exceeds_amount_returns_fixed_message(api, sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")

    inv_b = _invoice(sb_client, chapter_id, member, 1000)
    sub = _balance_submission(sb_client, chapter_id, member, 1000)
    vp = pay_svc.verify_payment_v2(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=treasurer,
    )

    body = {
        "allocations": [{"invoice_id": inv_b["id"], "amount_cents": 5000}],
        "reason": "override too high",
    }
    resp = api(make_user(treasurer, chapter_id)).post(
        f"/api/treasury/payments/{vp['id']}/reallocate",
        json=body, headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Allocations total exceeds verified payment amount"
