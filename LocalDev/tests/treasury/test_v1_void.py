"""TREASURY V1 — void/waive (decision #5): Treasurer only, reason required, logged.

Service-level: tr_void_invoice semantics (reason mandatory, ledger + audit).
Endpoint-level: rbac gating — treasurer (via member_roles) passes, generic
officer is 403 on the new endpoints; the legacy waive route now requires a
reason body and the same permission.
"""

from __future__ import annotations

import pytest

from api.treasury.services import invoices as svc
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401


@pytest.fixture(autouse=True)
def _stub_recompute(monkeypatch):
    monkeypatch.setattr(svc, "recompute_member_balance", lambda sb, member_id: None)


def _make_invoice(sb_client, chapter_id, member_id, amount=5000, kind="dues"):
    return svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind=kind,
        amount_cents=amount, description=None, actor_id=member_id,
    )


# ── service / RPC semantics ───────────────────────────────────────────────────
def test_void_requires_reason(sb_client, chapter_id, member_id):
    inv = _make_invoice(sb_client, chapter_id, member_id)
    with pytest.raises(Exception):
        svc.void_invoice(
            sb_client, chapter_id=chapter_id, invoice_id=inv["id"],
            actor_id=member_id, reason=None,
        )
    with pytest.raises(Exception):
        svc.void_invoice(
            sb_client, chapter_id=chapter_id, invoice_id=inv["id"],
            actor_id=member_id, reason="   ",
        )


def test_void_sets_cancelled_and_writes_ledger_and_audit_with_reason(
    sb_client, cursor, chapter_id, member_id
):
    inv = _make_invoice(sb_client, chapter_id, member_id)
    voided = svc.void_invoice(
        sb_client, chapter_id=chapter_id, invoice_id=inv["id"],
        actor_id=member_id, reason="member was abroad all year",
    )
    assert voided["status"] == "cancelled"

    cursor.execute(
        "SELECT * FROM big_ledger WHERE chapter_id=%s AND source_id=%s AND entry_type='CANCEL_INVOICE'",
        (chapter_id, inv["id"]),
    )
    ledger = cursor.fetchall()
    assert len(ledger) == 1
    assert ledger[0]["amount_cents"] == -5000

    cursor.execute(
        "SELECT * FROM audit_logs WHERE chapter_id=%s AND target_id=%s AND action='CANCEL_INVOICE'",
        (chapter_id, inv["id"]),
    )
    audit = cursor.fetchall()
    assert len(audit) == 1
    assert audit[0]["metadata"]["reason"] == "member was abroad all year"


def test_void_allowed_on_partially_paid(sb_client, cursor, chapter_id, member_id):
    inv = _make_invoice(sb_client, chapter_id, member_id)
    cursor.execute("UPDATE unpaid_invoices SET status='partially_paid' WHERE id=%s", (inv["id"],))
    voided = svc.void_invoice(
        sb_client, chapter_id=chapter_id, invoice_id=inv["id"],
        actor_id=member_id, reason="charged in error",
    )
    assert voided["status"] == "cancelled"


def test_void_refused_on_paid(sb_client, cursor, chapter_id, member_id):
    inv = _make_invoice(sb_client, chapter_id, member_id)
    cursor.execute("UPDATE unpaid_invoices SET status='paid' WHERE id=%s", (inv["id"],))
    with pytest.raises(Exception):
        svc.void_invoice(
            sb_client, chapter_id=chapter_id, invoice_id=inv["id"],
            actor_id=member_id, reason="nope",
        )


def test_void_idempotent_on_already_cancelled(sb_client, chapter_id, member_id):
    inv = _make_invoice(sb_client, chapter_id, member_id)
    svc.void_invoice(
        sb_client, chapter_id=chapter_id, invoice_id=inv["id"],
        actor_id=member_id, reason="first",
    )
    again = svc.void_invoice(
        sb_client, chapter_id=chapter_id, invoice_id=inv["id"],
        actor_id=member_id, reason="second",
    )
    assert again["status"] == "cancelled"


# ── endpoint gating: POST /api/treasury/invoices/{id}/void ───────────────────
def test_void_endpoint_treasurer_passes(api, sb_client, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    debtor = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    inv = _make_invoice(sb_client, chapter_id, debtor)

    client = api(make_user(treasurer, chapter_id))
    resp = client.post(
        f"/api/treasury/invoices/{inv['id']}/void",
        json={"reason": "issued twice"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "void"
    assert body["raw_status"] == "cancelled"


def test_void_endpoint_generic_officer_403(api, sb_client, cursor, chapter_id, member_factory):
    officer = member_factory(role="officer")
    debtor = member_factory()
    inv = _make_invoice(sb_client, chapter_id, debtor)

    client = api(make_user(officer, chapter_id, role="officer"))
    resp = client.post(
        f"/api/treasury/invoices/{inv['id']}/void",
        json={"reason": "should not work"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 403


def test_void_endpoint_empty_reason_422(api, sb_client, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    inv = _make_invoice(sb_client, chapter_id, treasurer)

    client = api(make_user(treasurer, chapter_id))
    resp = client.post(
        f"/api/treasury/invoices/{inv['id']}/void",
        json={"reason": "   "},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 422


def test_void_endpoint_paid_invoice_returns_fixed_message(api, sb_client, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    inv = _make_invoice(sb_client, chapter_id, treasurer)
    cursor.execute("UPDATE unpaid_invoices SET status='paid' WHERE id=%s", (inv["id"],))

    client = api(make_user(treasurer, chapter_id))
    resp = client.post(
        f"/api/treasury/invoices/{inv['id']}/void",
        json={"reason": "try voiding paid"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Only unpaid or partially paid invoices may be voided"


# ── legacy waive route: same permission + reason body ─────────────────────────
def test_waive_route_requires_reason_and_treasurer(api, sb_client, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    debtor = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    fine = _make_invoice(sb_client, chapter_id, debtor, amount=2500, kind="fine")

    client = api(make_user(treasurer, chapter_id))
    # missing body → 422
    resp = client.post(f"/api/fines/{fine['id']}/waive", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 422

    resp = client.post(
        f"/api/fines/{fine['id']}/waive",
        json={"reason": "excused after the fact"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (fine["id"],))
    assert cursor.fetchone()["status"] == "cancelled"


def test_waive_route_generic_officer_403(api, sb_client, cursor, chapter_id, member_factory):
    officer = member_factory(role="officer")
    debtor = member_factory()
    fine = _make_invoice(sb_client, chapter_id, debtor, amount=2500, kind="fine")

    client = api(make_user(officer, chapter_id, role="officer"))
    resp = client.post(
        f"/api/fines/{fine['id']}/waive",
        json={"reason": "officer cannot"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 403


def test_waive_route_not_found_returns_fixed_message(api, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    client = api(make_user(treasurer, chapter_id))
    resp = client.post(
        "/api/fines/00000000-0000-0000-0000-000000000000/waive",
        json={"reason": "does not exist"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Fine not found or cannot be waived"
