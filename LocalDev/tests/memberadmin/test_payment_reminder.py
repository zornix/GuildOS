"""POST /api/memberadmin/remind/{member_id} — gating and amounts (issue #35).

Three regressions, all in one endpoint:

1. It enqueued unconditionally. A member who owed nothing got an SMS demanding
   "$0.00" and — worse — the enqueue consumed the day-scoped dedup_key
   ("PAYMENT_REMINDER:{member}:{YYYY-MM-DD}"), so the *real* reminder an officer
   sent an hour later was silently swallowed until tomorrow.
2. The query filtered `kind='fine'`, so a member owing dues read as clean.
3. The query filtered `status='unpaid'`, so a `partially_paid` invoice was
   invisible; and summing `amount_cents` would have overstated what is still
   owed on one.

Real FastAPI app + real Postgres, following `tests/memberadmin/test_engagement_fines.py`:
DB fixtures come from `tests/memberadmin/conftest.py` (the re-exported treasury
harness) and `api`/`assign_role`/`make_user` from the treasury helpers. Partial
payment goes through the production service path (create → submit → verify)
rather than hand-setting a status.
"""

from __future__ import annotations

from datetime import date

from api.treasury.services import invoices as inv_svc
from api.treasury.services import payments as pay_svc
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401


def _officer_client(api, cursor, chapter_id, member_factory):
    officer = member_factory()
    assign_role(cursor, chapter_id, officer, "officer")  # holds standing:remind (0147)
    return api(make_user(officer, chapter_id))


def _remind(client, member_id):
    resp = client.post(
        f"/api/memberadmin/remind/{member_id}",
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _dedup_key(member_id: str) -> str:
    return f"PAYMENT_REMINDER:{member_id}:{date.today().isoformat()}"


def _outbox_rows(cursor, member_id):
    cursor.execute(
        "SELECT payload FROM message_outbox WHERE dedup_key = %s",
        (_dedup_key(member_id),),
    )
    return cursor.fetchall()


def test_nothing_outstanding_sends_nothing_and_leaves_the_dedup_key_unused(
    api, sb_client, cursor, chapter_id, member_factory
):
    """A clean member gets no message — and today's key is still spendable.

    The second half is the part that matters: an officer issues a real charge an
    hour later and the reminder still goes out. Before the fix the $0.00 send had
    already burned the key and this second call returned queued=False.
    """
    client = _officer_client(api, cursor, chapter_id, member_factory)
    clean = member_factory()

    first = _remind(client, clean)
    assert first["queued"] is False
    assert first["unpaid_count"] == 0
    assert first["unpaid_total_cents"] == 0
    assert "Nothing outstanding" in first["message"]
    assert _outbox_rows(cursor, clean) == []

    # A real charge lands later the same day; the reminder must still queue.
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=clean, kind="fine",
        amount_cents=2500, description="Missed meeting", actor_id=clean,
    )
    second = _remind(client, clean)
    assert second["queued"] is True
    assert second["unpaid_count"] == 1
    assert second["unpaid_total_cents"] == 2500
    assert len(_outbox_rows(cursor, clean)) == 1


def test_unpaid_dues_are_counted_not_just_fines(
    api, sb_client, cursor, chapter_id, member_factory
):
    """kind='dues' is money owed. The old kind='fine' filter reported $0.00."""
    client = _officer_client(api, cursor, chapter_id, member_factory)
    duespayer = member_factory()
    inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=duespayer, kind="dues",
        amount_cents=5000, description="Fall dues", actor_id=duespayer,
    )

    body = _remind(client, duespayer)
    assert body["queued"] is True
    assert body["unpaid_count"] == 1
    assert body["unpaid_total_cents"] == 5000

    payload = _outbox_rows(cursor, duespayer)[0]["payload"]
    assert payload["unpaid_count"] == 1
    assert payload["unpaid_total_cents"] == 5000


def test_partially_paid_fine_counts_at_its_remaining_balance(
    api, sb_client, cursor, chapter_id, member_factory
):
    """$50 fine, $20 verified → $30 remaining, not $50 and not invisible."""
    client = _officer_client(api, cursor, chapter_id, member_factory)
    payer = member_factory()
    invoice = inv_svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=payer, kind="fine",
        amount_cents=5000, description="Missed formal", actor_id=payer,
    )
    submission = inv_svc.submit_payment(
        sb_client, chapter_id=chapter_id, member_id=payer, invoice_id=invoice["id"],
        claimed_amount_cents=2000, method="venmo", proof_ref="ref-1", actor_id=payer,
    )
    pay_svc.verify_payment(
        sb_client, chapter_id=chapter_id, submission_id=submission["id"], actor_id=payer
    )
    cursor.execute("SELECT status FROM unpaid_invoices WHERE id=%s", (invoice["id"],))
    assert cursor.fetchone()["status"] == "partially_paid"

    body = _remind(client, payer)
    assert body["queued"] is True
    assert body["unpaid_count"] == 1
    assert body["unpaid_total_cents"] == 3000  # 5000 - 2000, not amount_cents
