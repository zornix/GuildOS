"""F-014 (server half) / D1 — an officer records a payment for a member in one step.

POST /api/treasury/payments/record = submit + verify-v2 in one transaction
(tr_record_payment). Contract: 00-README "Record payment".
"""

from __future__ import annotations

import uuid

import pytest

from api.treasury.services import invoices as inv_svc
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401

URL = "/api/treasury/payments/record"


@pytest.fixture(autouse=True)
def _stub_invoice_recompute(monkeypatch):
    monkeypatch.setattr(inv_svc, "recompute_member_balance", lambda sb, member_id: None)


@pytest.fixture
def officer(cursor, chapter_id, member_factory):
    officer = member_factory()
    assign_role(cursor, chapter_id, officer, "treasurer")
    return officer


def _invoice(sb_client, chapter_id, member_id, amount):
    return inv_svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=amount, description=None, actor_id=member_id,
    )


def _record(api, user_id, chapter_id, body, key=None):
    headers = {"Authorization": "Bearer x"}
    if key:
        headers["Idempotency-Key"] = key
    return api(make_user(user_id, chapter_id)).post(URL, json=body, headers=headers)


def _status(cursor, invoice_id):
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice_id,))
    return cursor.fetchone()["status"]


def _count(cursor, table, member_id):
    cursor.execute(f"SELECT count(*) AS n FROM {table} WHERE member_id=%s", (member_id,))
    return cursor.fetchone()["n"]


def test_record_payment_against_invoice_pays_it(api, sb_client, cursor, chapter_id, member_id, officer):
    inv = _invoice(sb_client, chapter_id, member_id, 7500)

    resp = _record(api, officer, chapter_id, {
        "member_id": member_id, "amount_cents": 7500, "method": "cash",
        "invoice_id": inv["id"], "reference": "cash at meeting",
    })

    assert resp.status_code == 200, resp.text
    vp = resp.json()
    assert vp["amount_cents"] == 7500 and vp["allocated_cents"] == 7500
    assert _status(cursor, inv["id"]) == "paid"
    assert _count(cursor, "verified_payments", member_id) == 1
    cursor.execute("SELECT status, invoice_id FROM payment_submissions WHERE member_id=%s", (member_id,))
    subs = cursor.fetchall()
    assert [(s["status"], str(s["invoice_id"])) for s in subs] == [("approved", inv["id"])]
    cursor.execute(
        "SELECT actor_id FROM audit_logs WHERE chapter_id=%s AND target_id=%s", (chapter_id, vp["id"])
    )
    actors = {str(r["actor_id"]) for r in cursor.fetchall()}
    assert actors == {officer}


def test_record_payment_without_invoice_allocates_oldest_first(
    api, sb_client, cursor, chapter_id, member_id, officer
):
    inv_a = _invoice(sb_client, chapter_id, member_id, 3000)  # oldest
    inv_b = _invoice(sb_client, chapter_id, member_id, 3000)

    resp = _record(api, officer, chapter_id, {
        "member_id": member_id, "amount_cents": 4000, "method": "venmo",
    })

    assert resp.status_code == 200, resp.text
    assert _status(cursor, inv_a["id"]) == "paid"
    assert _status(cursor, inv_b["id"]) == "partially_paid"


def test_record_payment_is_atomic(api, sb_client, cursor, chapter_id, member_factory, officer):
    member, other = member_factory(), member_factory()
    others_invoice = _invoice(sb_client, chapter_id, other, 3000)

    resp = _record(api, officer, chapter_id, {
        "member_id": member, "amount_cents": 3000, "method": "cash",
        "invoice_id": others_invoice["id"],
    })

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] != "Not Found"  # our mapping, not a missing route
    assert _count(cursor, "payment_submissions", member) == 0
    assert _count(cursor, "verified_payments", member) == 0


def test_record_payment_against_paid_invoice_is_409(api, sb_client, cursor, chapter_id, member_id, officer):
    inv = _invoice(sb_client, chapter_id, member_id, 2000)
    body = {"member_id": member_id, "amount_cents": 2000, "method": "cash", "invoice_id": inv["id"]}
    assert _record(api, officer, chapter_id, body).status_code == 200

    resp = _record(api, officer, chapter_id, body)

    assert resp.status_code == 409, resp.text
    assert _count(cursor, "verified_payments", member_id) == 1


def test_record_payment_idempotent(api, sb_client, cursor, chapter_id, member_id, officer, monkeypatch):
    from api.treasury.services import payments as pay_svc

    calls = []
    monkeypatch.setattr(pay_svc, "notify_payment_approved", lambda **kw: calls.append(kw))
    _invoice(sb_client, chapter_id, member_id, 5000)
    body = {"member_id": member_id, "amount_cents": 5000, "method": "zelle"}
    key = f"rec-{uuid.uuid4()}"

    first = _record(api, officer, chapter_id, body, key=key)
    second = _record(api, officer, chapter_id, body, key=key)

    assert first.status_code == 200 and second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    assert _count(cursor, "verified_payments", member_id) == 1
    assert _count(cursor, "payment_submissions", member_id) == 1
    assert len(calls) == 1


def test_record_payment_requires_permission(api, cursor, chapter_id, member_factory):
    plain, member = member_factory(), member_factory()

    resp = _record(api, plain, chapter_id, {
        "member_id": member, "amount_cents": 1000, "method": "cash",
    })

    assert resp.status_code == 403
    assert _count(cursor, "payment_submissions", member) == 0


def test_record_payment_cross_chapter_member_404(api, cursor, chapter_id, officer):
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES (%s, 'Other Org', 'Other U') RETURNING id",
        (f"tr-test-{uuid.uuid4()}",),
    )
    other_chapter = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO members (chapter_id, name, email, role, status) "
        "VALUES (%s, 'Outsider', %s, 'member', 'active') RETURNING id",
        (other_chapter, f"{uuid.uuid4()}@test.local"),
    )
    outsider = str(cursor.fetchone()["id"])

    resp = _record(api, officer, chapter_id, {
        "member_id": outsider, "amount_cents": 1000, "method": "cash",
    })

    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] != "Not Found"
    assert _count(cursor, "payment_submissions", outsider) == 0
