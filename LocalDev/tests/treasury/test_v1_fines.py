"""TREASURY V1 — fines: flat $25, never automatic, ≥24h gate (spec §5).

System surfaces who missed (GET /api/fines/missed/{event_id}); Finance Board
issues fine invoices by hand (POST /api/fines/issue). The auto-fine cron is a
disabled no-op.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from api.treasury.core.fines import FLAT_FINE_CENTS
from api.treasury.services import invoices as inv_svc
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _stub_recompute(monkeypatch):
    monkeypatch.setattr(inv_svc, "recompute_member_balance", lambda sb, member_id: None)


def _make_event(cursor, chapter_id, *, hours_ago: float, required: bool = True) -> str:
    start = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).astimezone(ZoneInfo("America/Los_Angeles"))
    cursor.execute(
        """INSERT INTO events (chapter_id, title, description, date, time, location, required, fine_amount)
           VALUES (%s, 'Chapter Meeting', '', %s, %s, 'Hall', %s, 0) RETURNING id""",
        (chapter_id, start.date(), start.time(), required),
    )
    return str(cursor.fetchone()["id"])


def _check_in(cursor, event_id, member_id):
    cursor.execute(
        "INSERT INTO attendance (event_id, member_id, checked_in) VALUES (%s,%s,true)",
        (event_id, member_id),
    )


def test_flat_fine_constant_is_25_dollars():
    assert FLAT_FINE_CENTS == 2500


def test_missed_endpoint_surfaces_unexcused_and_already_fined(
    api, sb_client, cursor, chapter_id, member_factory
):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    attended = member_factory()
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30)
    _check_in(cursor, event_id, attended)

    client = api(make_user(treasurer, chapter_id))
    resp = client.get(f"/api/fines/missed/{event_id}", headers={"Authorization": "Bearer x"})
    assert resp.status_code == 200, resp.text
    rows = resp.json()["missed"]
    ids = {r["member_id"] for r in rows}
    assert missed in ids and treasurer in ids
    assert attended not in ids
    assert all(r["already_fined"] is False for r in rows)

    # issue a fine to `missed`, then the flag flips
    issue = client.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert issue.status_code == 200, issue.text
    rows = client.get(
        f"/api/fines/missed/{event_id}", headers={"Authorization": "Bearer x"}
    ).json()["missed"]
    flags = {r["member_id"]: r["already_fined"] for r in rows}
    assert flags[missed] is True


def test_missed_endpoint_requires_fines_issue_permission(
    api, sb_client, cursor, chapter_id, member_factory
):
    # A plain member holds no treasury key. (Not a generic officer: 0147 grants
    # the officer role treasury:fines:issue outright, preserving the access it
    # had through the deleted require_officer gate.)
    plain = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30)
    resp = api(make_user(plain, chapter_id)).get(
        f"/api/fines/missed/{event_id}", headers={"Authorization": "Bearer x"}
    )
    assert resp.status_code == 403


def test_issue_rejected_before_24h(api, sb_client, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=2)  # too recent

    resp = api(make_user(treasurer, chapter_id)).post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 422
    assert "24" in resp.json()["detail"]


def test_issue_creates_flat_2500_fines_for_unexcused_only(
    api, sb_client, cursor, chapter_id, member_factory
):
    finance = member_factory()
    assign_role(cursor, chapter_id, finance, "finance_board")  # finance_board may issue
    attended = member_factory()
    missed_1 = member_factory()
    missed_2 = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=26)
    _check_in(cursor, event_id, attended)

    client = api(make_user(finance, chapter_id))
    resp = client.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [attended, missed_1, missed_2]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body["issued_member_ids"]) == {missed_1, missed_2}
    assert attended in body["skipped_member_ids"]

    cursor.execute(
        "SELECT member_id, amount_cents, kind, issued_by FROM unpaid_invoices WHERE source_event_id=%s",
        (event_id,),
    )
    rows = cursor.fetchall()
    assert len(rows) == 2
    assert {str(r["member_id"]) for r in rows} == {missed_1, missed_2}
    assert all(r["amount_cents"] == 2500 for r in rows)
    assert all(r["kind"] == "fine" for r in rows)
    assert all(str(r["issued_by"]) == finance for r in rows)

    # re-issuing skips the already-fined members
    resp = client.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed_1, missed_2]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 200
    assert resp.json()["issued_member_ids"] == []
    cursor.execute(
        "SELECT count(*) AS n FROM unpaid_invoices WHERE source_event_id=%s", (event_id,)
    )
    assert cursor.fetchone()["n"] == 2


def test_list_fines_presents_client_shape_with_member_and_event(
    api, sb_client, cursor, chapter_id, member_factory
):
    """GET /api/fines returns the presented fine shape the frontend adapts:
    money as integer `amount_cents`, `reason`/`issued_at` renamed, and member/
    event names stitched in (the raw unpaid_invoices row carries none of these)."""
    finance = member_factory()
    assign_role(cursor, chapter_id, finance, "finance_board")
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30)  # required, "Chapter Meeting"

    issuer = api(make_user(finance, chapter_id))
    issued = issuer.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert issued.status_code == 200, issued.text

    # Officer view: all chapter fines, presented.
    officer = api(make_user(member_factory(role="officer"), chapter_id, role="officer"))
    rows = officer.get("/api/fines", headers={"Authorization": "Bearer x"}).json()
    assert len(rows) == 1
    fine = rows[0]
    assert fine["amount_cents"] == 2500          # integer cents, not `amount`
    assert fine["status"] == "unpaid"
    assert str(fine["member_id"]) == missed
    assert fine["member_name"]                    # stitched member name
    assert fine["event_title"] == "Chapter Meeting"
    assert fine["event_date"]
    assert "Chapter Meeting" in fine["reason"]    # description → reason
    assert fine["issued_at"]                      # created_at → issued_at
    # The stale field names are gone.
    assert "amount" not in fine and "description" not in fine and "created_at" not in fine


def test_list_fines_scopes_members_to_their_own(
    api, sb_client, cursor, chapter_id, member_factory
):
    finance = member_factory()
    assign_role(cursor, chapter_id, finance, "finance_board")
    mine = member_factory()
    other = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30)

    issuer = api(make_user(finance, chapter_id))
    issuer.post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [mine, other]},
        headers={"Authorization": "Bearer x"},
    )

    rows = api(make_user(mine, chapter_id)).get(
        "/api/fines", headers={"Authorization": "Bearer x"}
    ).json()
    assert {str(r["member_id"]) for r in rows} == {mine}
    assert all(r["amount_cents"] == 2500 for r in rows)


def test_issue_refused_for_non_required_event(api, sb_client, cursor, chapter_id, member_factory):
    treasurer = member_factory()
    assign_role(cursor, chapter_id, treasurer, "treasurer")
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30, required=False)
    resp = api(make_user(treasurer, chapter_id)).post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 422


def test_issue_requires_permission(api, sb_client, cursor, chapter_id, member_factory):
    plain = member_factory()  # no treasury:fines:issue (see the missed-endpoint test)
    missed = member_factory()
    event_id = _make_event(cursor, chapter_id, hours_ago=30)
    resp = api(make_user(plain, chapter_id)).post(
        "/api/fines/issue",
        json={"event_id": event_id, "member_ids": [missed]},
        headers={"Authorization": "Bearer x"},
    )
    assert resp.status_code == 403


# ── automatic fines are dead ──────────────────────────────────────────────────
def test_cron_process_fines_is_disabled(
    api, sb_client, chapter_id, member_factory, monkeypatch
):
    # Since 0150 every /api/cron route is gated by CRON_SECRET, not by a member
    # session, so the caller here is the cron runner rather than a logged-in user.
    from api.config import settings

    monkeypatch.setattr(settings, "CRON_SECRET", "test-cron-secret")
    member = member_factory()
    resp = api(make_user(member, chapter_id)).get(
        "/api/cron/process-fines",
        headers={"Authorization": "Bearer test-cron-secret"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "disabled"


def test_vercel_json_has_no_process_fines_cron():
    config = json.loads((_REPO_ROOT / "vercel.json").read_text())
    for cron in config.get("crons", []):
        assert "process-fines" not in cron.get("path", "")


def test_list_fines_reports_remaining_cents_after_a_partial_payment(
    api, sb_client, cursor, chapter_id, member_factory
):
    """Mark paid must send what is still owed, not the face amount: each fine
    row carries `remaining_cents` from its payment allocations."""
    from api.treasury.services import payments as pay_svc

    debtor = member_factory()
    part = inv_svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=debtor, kind="fine",
        amount_cents=2500, description="Late", actor_id=debtor,
    )
    sub = pay_svc.submit_balance_payment(
        sb_client, chapter_id=chapter_id, member_id=debtor,
        claimed_amount_cents=1000, method="cash", proof_ref=None,
    )
    pay_svc.verify_payment_v2(sb_client, chapter_id=chapter_id, submission_id=sub["id"], actor_id=debtor)
    untouched = inv_svc.create_invoice_v2(
        sb_client, chapter_id=chapter_id, member_id=debtor, kind="fine",
        amount_cents=2500, description="Noise", actor_id=debtor,
    )

    officer = api(make_user(member_factory(role="officer"), chapter_id, role="officer"))
    rows = officer.get("/api/fines", headers={"Authorization": "Bearer x"}).json()
    remaining = {str(r["id"]): r["remaining_cents"] for r in rows}
    assert remaining == {part["id"]: 1500, untouched["id"]: 2500}


def test_issue_is_all_or_nothing(api, sb_client, cursor, chapter_id, member_factory, monkeypatch):
    import uuid
    import api.treasury.api.fines_legacy as route
    from api.platform.postgres import _RpcBuilder

    actor = member_factory(role="officer")
    members = [member_factory(), member_factory(), str(uuid.uuid4())]
    event = _make_event(cursor, chapter_id, hours_ago=30)
    # Inject a stale absence list so the invalid final member reaches the RPC.
    monkeypatch.setattr(route, "list_unexcused_absences",
                        lambda *args, **kwargs: [{"member_id": member} for member in members])
    calls = []
    execute = _RpcBuilder.execute

    def tracked_rpc(query):
        if query._function_name == "tr_issue_event_fines":
            calls.append(query._params["p_member_ids"])
        return execute(query)

    monkeypatch.setattr(_RpcBuilder, "execute", tracked_rpc)
    response = api(make_user(actor, chapter_id, role="officer")).post(
        "/api/fines/issue", json={"event_id": event, "member_ids": members},
    )
    assert response.status_code == 500
    assert calls == [members]
    cursor.execute('SELECT count(*) AS n FROM unpaid_invoices WHERE chapter_id=%s AND source_event_id=%s',
                   (chapter_id, event))
    assert cursor.fetchone()['n'] == 0
    cursor.execute("SELECT count(*) AS n FROM audit_logs WHERE chapter_id=%s AND action='CREATE_INVOICE'",
                   (chapter_id,))
    assert cursor.fetchone()['n'] == 0
    cursor.execute("SELECT count(*) AS n FROM big_ledger WHERE chapter_id=%s AND entry_type='INVOICE_CREATED'", (chapter_id,))
    assert cursor.fetchone()['n'] == 0
    cursor.execute("SELECT count(*) AS n FROM message_outbox WHERE chapter_id=%s", (chapter_id,))
    assert cursor.fetchone()['n'] == 0


def test_reissue_skips_everyone_and_creates_nothing(api, sb_client, cursor, chapter_id, member_factory):
    actor = member_factory(role='officer')
    members = [member_factory() for _ in range(3)]
    event = _make_event(cursor, chapter_id, hours_ago=30)
    client = api(make_user(actor, chapter_id, role='officer'))
    for attempt in range(2):
        response = client.post('/api/fines/issue', json={'event_id': event, 'member_ids': members})
        assert response.status_code == 200, response.text
        if attempt:
            assert set(response.json()['skipped_member_ids']) == set(members)
            assert response.json()['invoices'] == []
    cursor.execute('SELECT count(*) AS n FROM unpaid_invoices WHERE chapter_id=%s AND source_event_id=%s', (chapter_id,event))
    assert cursor.fetchone()['n'] == 3


def test_issue_queues_one_notice_per_fined_member(api, sb_client, cursor, chapter_id, member_factory):
    actor = member_factory(role='officer')
    members = [member_factory() for _ in range(3)]
    event = _make_event(cursor, chapter_id, hours_ago=30)
    client = api(make_user(actor, chapter_id, role='officer'))
    response = client.post('/api/fines/issue', json={'event_id': event, 'member_ids': members})
    assert response.status_code == 200, response.text
    cursor.execute("SELECT member_id,target_id,event_type,channel FROM message_outbox WHERE chapter_id=%s", (chapter_id,))
    notices = cursor.fetchall()
    assert len(notices) == 3
    assert {str(n['member_id']) for n in notices} == set(members)
    assert {str(n['target_id']) for n in notices} == {i['id'] for i in response.json()['invoices']}
    assert all(n['event_type'] == 'INVOICE_ISSUED' and n['channel'] == 'email' for n in notices)
    response = client.post('/api/fines/issue', json={'event_id': event, 'member_ids': members})
    assert response.status_code == 200, response.text
    cursor.execute('SELECT count(*) AS n FROM message_outbox WHERE chapter_id=%s', (chapter_id,))
    assert cursor.fetchone()['n'] == 3


def test_process_event_route_is_gone(api, sb_client, cursor, chapter_id, member_factory):
    actor = member_factory(role='officer')
    event = _make_event(cursor, chapter_id, hours_ago=30)
    response = api(make_user(actor, chapter_id, role='officer')).post(f'/api/fines/process-event/{event}')
    assert response.status_code in (404,405)


def test_fine_gate_uses_chapter_timezone(api, sb_client, cursor, chapter_id, member_factory):
    actor, member = member_factory(role='officer'), member_factory()
    client = api(make_user(actor, chapter_id, role='officer'))
    for hours, expected in ((20,422),(25,200)):
        local = (datetime.now(timezone.utc)-timedelta(hours=hours)).astimezone(ZoneInfo('America/Los_Angeles'))
        event = _make_event(cursor, chapter_id, hours_ago=hours)
        cursor.execute('UPDATE events SET date=%s,time=%s WHERE id=%s', (local.date(),local.time(),event))
        response = client.post('/api/fines/issue', json={'event_id':event,'member_ids':[member]})
        assert response.status_code == expected, response.text
        missed = client.get(f'/api/fines/missed/{event}').json()
        assert missed['finable_now'] == (expected == 200)
        assert datetime.fromisoformat(missed['event_start']) == local.astimezone(timezone.utc)


def test_fine_summary_counts_remaining_after_one_cent_payment(api, sb_client, cursor, chapter_id, member_factory):
    actor, member = member_factory(role='officer'), member_factory()
    invoice = inv_svc.create_invoice_v2(sb_client, chapter_id=chapter_id, member_id=member,
                                       kind='fine', amount_cents=2500, description='Missed', actor_id=actor)
    cursor.execute("SELECT tr_record_payment(%s,%s,1,'cash',%s,%s,NULL,NULL)", (chapter_id,member,actor,invoice['id']))
    response = api(make_user(actor, chapter_id, role='officer')).get('/api/fines/summary')
    assert response.status_code == 200, response.text
    assert response.json()['total_unpaid_cents'] == 2499
    assert response.json()['count_unpaid'] == 1


def test_fine_reads_use_shared_remaining_helper(api, sb_client, cursor, chapter_id, member_factory, monkeypatch):
    import api.treasury.services.remaining as remaining
    calls = []
    original = remaining.remaining_by_invoice
    def tracked(sb, invoices):
        calls.append([i['id'] for i in invoices])
        return original(sb, invoices)
    monkeypatch.setattr(remaining, 'remaining_by_invoice', tracked)
    actor = member_factory(role='officer')
    invoice = inv_svc.create_invoice_v2(sb_client, chapter_id=chapter_id, member_id=actor,
                                       kind='fine', amount_cents=2500, description='Missed', actor_id=actor)
    client = api(make_user(actor, chapter_id, role='officer'))
    assert client.get('/api/fines/').status_code == 200
    assert client.get('/api/fines/summary').status_code == 200
    assert calls == [[invoice['id']], [invoice['id']]]
