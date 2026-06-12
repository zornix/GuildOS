"""TREASURY V1 — balance-level payment submissions, evidence, member dashboard.

Spec: a member submits amount + method + evidence against their OVERALL balance
(invoice_id NULL); it is visible as "pending balance" on their dashboard until a
Finance Board member verifies it.
"""

from __future__ import annotations

import base64
import uuid

import pytest

from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc
from api.treasury.services.member_dashboard import get_member_dashboard
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401


@pytest.fixture(autouse=True)
def _stub_recompute(monkeypatch):
    monkeypatch.setattr(inv_svc, "recompute_member_balance", lambda sb, member_id: None)


# ── balance submissions ───────────────────────────────────────────────────────
def test_submit_balance_payment_creates_pending_with_null_invoice(
    sb_client, cursor, chapter_id, member_id
):
    sub = pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=7500, method="venmo", proof_ref="venmo memo #123",
    )
    assert sub["status"] == "pending"
    assert sub["invoice_id"] is None
    assert sub["claimed_amount_cents"] == 7500

    # no money moved
    cursor.execute(
        "SELECT count(*) AS n FROM verified_payments WHERE chapter_id=%s", (chapter_id,)
    )
    assert cursor.fetchone()["n"] == 0


def test_submit_balance_payment_accepts_check_method(sb_client, chapter_id, member_id):
    sub = pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=2500, method="check", proof_ref="check #1042",
    )
    assert sub["method"] == "check"


def test_submit_balance_payment_tenant_guard(sb_client, cursor, chapter_id, member_id):
    # a member of ANOTHER chapter cannot be attributed a submission in this chapter
    cursor.execute(
        "INSERT INTO chapters (name, organization, school) VALUES (%s,'O','U') RETURNING id",
        (f"other-{uuid.uuid4()}",),
    )
    other_chapter = str(cursor.fetchone()["id"])
    cursor.execute(
        """INSERT INTO members (chapter_id, name, email, role, status)
           VALUES (%s,'Outsider',%s,'member','active') RETURNING id""",
        (other_chapter, f"{uuid.uuid4()}@x.local"),
    )
    outsider = str(cursor.fetchone()["id"])
    with pytest.raises(Exception):
        pay_svc.submit_balance_payment(
            sb_client, chapter_id=chapter_id, member_id=outsider,
            claimed_amount_cents=1000, method="cash", proof_ref=None,
        )


def test_balance_submission_idempotent(sb_client, chapter_id, member_id):
    key = f"bal-{uuid.uuid4()}"
    a = pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=1000, method="zelle", proof_ref=None, idempotency_key=key,
    )
    b = pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=1000, method="zelle", proof_ref=None, idempotency_key=key,
    )
    assert a["id"] == b["id"]


# ── evidence ──────────────────────────────────────────────────────────────────
def test_evidence_stored_and_size_capped(sb_client, cursor, chapter_id, member_id):
    sub = pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=1000, method="venmo", proof_ref=None,
    )
    ev = pay_svc.add_evidence(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"],
        content_type="image/png", data=b"\x89PNG fake bytes",
    )
    assert ev["size_bytes"] == len(b"\x89PNG fake bytes")

    fetched = pay_svc.get_evidence(sb_client, chapter_id=chapter_id, evidence_id=ev["id"])
    assert fetched["content_type"] == "image/png"
    assert base64.b64decode(fetched["data_base64"]) == b"\x89PNG fake bytes"

    # > 2 MiB is refused
    with pytest.raises(Exception):
        pay_svc.add_evidence(
            sb_client, chapter_id=chapter_id, submission_id=sub["id"],
            content_type="image/png", data=b"x" * (2 * 1024 * 1024 + 1),
        )


def test_evidence_is_append_only(sb_client, cursor, chapter_id, member_id):
    sub = pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=1000, method="venmo", proof_ref=None,
    )
    ev = pay_svc.add_evidence(
        sb_client, chapter_id=chapter_id, submission_id=sub["id"],
        content_type="text/plain", data=b"memo",
    )
    with pytest.raises(Exception):
        cursor.execute("UPDATE payment_evidence SET content_type='x' WHERE id=%s", (ev["id"],))
    with pytest.raises(Exception):
        cursor.execute("DELETE FROM payment_evidence WHERE id=%s", (ev["id"],))


# ── member dashboard ──────────────────────────────────────────────────────────
def test_dashboard_shows_pending_balance_and_open_invoices(
    sb_client, cursor, chapter_id, member_id, monkeypatch
):
    monkeypatch.undo()  # real recompute for balance figures
    from datetime import datetime, timedelta, timezone

    past_due = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    inv = inv_svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=member_id, kind="dues",
        amount_cents=5000, description="Spring dues", actor_id=member_id,
        due_at=past_due,
    )
    pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=member_id,
        claimed_amount_cents=3000, method="venmo", proof_ref=None,
    )

    dash = get_member_dashboard(sb_client, chapter_id=chapter_id, member_id=member_id)

    assert dash["pending_cents"] == 3000
    assert len(dash["pending_submissions"]) == 1
    assert dash["pending_submissions"][0]["state"] == "pending balance"

    open_invoices = dash["open_invoices"]
    assert len(open_invoices) == 1
    oi = open_invoices[0]
    assert oi["id"] == inv["id"]
    assert oi["amount_cents"] == 5000
    assert oi["remaining_cents"] == 5000
    assert oi["overdue"] is True  # decision #3: overdue invoices stay visible
    assert oi["source"] == "dues"

    assert dash["balance"]["total_owed_cents"] == 5000
    assert "recent_activity" in dash


# ── endpoints ─────────────────────────────────────────────────────────────────
def test_balance_submission_endpoint_self(api, sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    client = api(make_user(member, chapter_id))
    resp = client.post(
        "/api/treasury/payments/balance-submissions",
        json={"amount_cents": 4500, "method": "check", "proof_ref": "check #7"},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["invoice_id"] is None
    cursor.execute(
        "SELECT member_id FROM payment_submissions WHERE id=%s", (body["id"],)
    )
    assert str(cursor.fetchone()["member_id"]) == member


def test_evidence_endpoints_owner_and_reviewer(api, sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    stranger = member_factory()
    reviewer = member_factory()
    assign_role(cursor, chapter_id, reviewer, "finance_board")

    owner_client = api(make_user(member, chapter_id))
    sub = owner_client.post(
        "/api/treasury/payments/balance-submissions",
        json={"amount_cents": 1000, "method": "venmo"},
        headers={"Authorization": "Bearer x"},
    ).json()

    payload = base64.b64encode(b"proof-bytes").decode()
    ev = owner_client.post(
        f"/api/treasury/payments/submissions/{sub['id']}/evidence",
        json={"content_type": "image/jpeg", "data_base64": payload},
        headers={"Authorization": "Bearer x"},
    )
    assert ev.status_code == 200, ev.text
    ev_id = ev.json()["id"]

    # a stranger may not attach evidence to someone else's submission
    stranger_client = api(make_user(stranger, chapter_id))
    denied = stranger_client.post(
        f"/api/treasury/payments/submissions/{sub['id']}/evidence",
        json={"content_type": "image/jpeg", "data_base64": payload},
        headers={"Authorization": "Bearer x"},
    )
    assert denied.status_code == 403

    # owner and reviewer (finance_board → treasury:payment:verify) can read it
    owner_read = api(make_user(member, chapter_id)).get(
        f"/api/treasury/payments/evidence/{ev_id}", headers={"Authorization": "Bearer x"}
    )
    assert owner_read.status_code == 200
    reviewer_read = api(make_user(reviewer, chapter_id)).get(
        f"/api/treasury/payments/evidence/{ev_id}", headers={"Authorization": "Bearer x"}
    )
    assert reviewer_read.status_code == 200
    assert base64.b64decode(reviewer_read.json()["data_base64"]) == b"proof-bytes"

    # an unrelated member cannot
    stranger_read = api(make_user(stranger, chapter_id)).get(
        f"/api/treasury/payments/evidence/{ev_id}", headers={"Authorization": "Bearer x"}
    )
    assert stranger_read.status_code == 403


def test_dashboard_endpoint_auth(api, sb_client, cursor, chapter_id, member_factory):
    member = member_factory()
    other = member_factory()
    verifier = member_factory()
    assign_role(cursor, chapter_id, verifier, "treasurer")

    # self → 200
    resp = api(make_user(member, chapter_id)).get(
        f"/api/treasury/members/{member}/dashboard", headers={"Authorization": "Bearer x"}
    )
    assert resp.status_code == 200, resp.text
    assert "balance" in resp.json()

    # unrelated member → 403
    resp = api(make_user(other, chapter_id)).get(
        f"/api/treasury/members/{member}/dashboard", headers={"Authorization": "Bearer x"}
    )
    assert resp.status_code == 403

    # treasurer (treasury:payment:verify) → 200
    resp = api(make_user(verifier, chapter_id)).get(
        f"/api/treasury/members/{member}/dashboard", headers={"Authorization": "Bearer x"}
    )
    assert resp.status_code == 200
