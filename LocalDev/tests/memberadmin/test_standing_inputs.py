from api.memberadmin.core.engagement import load_member_engagement
from tests.memberadmin.test_engagement_fines import (
    _make_required_event,
    _insert_invoice,
    _row_for,
)
from tests.treasury.test_v1_helpers import api  # noqa: F401


async def test_partially_paid_fine_still_counts(
    api, sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    _make_required_event(cursor, chapter_id)
    cursor.execute(
        "INSERT INTO unpaid_invoices (chapter_id,member_id,kind,amount_cents,status) VALUES (%s,%s,'fine',2500,'partially_paid') RETURNING id",
        (chapter_id, member),
    )
    invoice = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id,member_id,amount_cents) VALUES (%s,%s,1) RETURNING id",
        (chapter_id, member),
    )
    payment = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO payment_allocations (chapter_id,verified_payment_id,invoice_id,amount_cents) VALUES (%s,%s,%s,1)",
        (chapter_id, payment, invoice),
    )
    row = _row_for(await load_member_engagement(chapter_id), member)
    assert (row.unpaid_fines, row.unpaid_amount_cents) == (1, 2499)


async def test_fines_count_with_no_past_required_event(
    api, sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    _insert_invoice(cursor, chapter_id, member, "fine", 2500)
    row = _row_for(await load_member_engagement(chapter_id), member)
    assert (row.unpaid_fines, row.unpaid_amount_cents, row.total_required) == (
        1,
        2500,
        0,
    )


async def test_paid_and_cancelled_fines_do_not_count(
    api, sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    _make_required_event(cursor, chapter_id)
    for status in ("paid", "cancelled"):
        cursor.execute(
            "INSERT INTO unpaid_invoices (chapter_id,member_id,kind,amount_cents,status) VALUES (%s,%s,'fine',2500,%s)",
            (chapter_id, member, status),
        )
    row = _row_for(await load_member_engagement(chapter_id), member)
    assert (row.unpaid_fines, row.unpaid_amount_cents) == (0, 0)


async def test_only_started_events_count(
    api, sb_client, cursor, chapter_id, member_factory
):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    member = member_factory()
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    for hours, total in ((3, 0), (-2, 1)):
        start = now + timedelta(hours=hours)
        cursor.execute(
            "INSERT INTO events (chapter_id,title,date,time,location,required) VALUES (%s,'Timed',%s,%s,'Hall',true)",
            (chapter_id, start.date(), start.time()),
        )
        row = _row_for(await load_member_engagement(chapter_id), member)
        assert (row.total_required, row.missed) == (total, total)


def test_excuse_approval_updates_cache(
    api, sb_client, cursor, chapter_id, member_factory
):
    from tests.treasury.test_v1_helpers import make_user
    from api.treasury.core.balance import BalanceEngine

    officer = member_factory(role="officer")
    member = member_factory()
    event = _make_required_event(cursor, chapter_id)
    client = api(make_user(officer, chapter_id, "officer"))
    response = client.post(
        "/api/fines/issue",
        json={"event_id": event, "member_ids": [member]},
        headers={"Authorization": "Bearer x"},
    )
    assert response.status_code == 200, response.text
    cursor.execute(
        "SELECT outstanding_balance_cents FROM member_finance_accounts WHERE member_id=%s",
        (member,),
    )
    assert cursor.fetchone()["outstanding_balance_cents"] == 2500
    cursor.execute(
        "INSERT INTO excuses (chapter_id,event_id,member_id,reason) VALUES (%s,%s,%s,'test') RETURNING id",
        (chapter_id, event, member),
    )
    excuse = str(cursor.fetchone()["id"])
    response = client.put(
        f"/api/excuses/{excuse}/review",
        json={"status": "approved"},
        headers={"Authorization": "Bearer x"},
    )
    assert response.status_code == 200, response.text
    assert BalanceEngine(sb_client).member_outstanding(member).cents == 0
    cursor.execute(
        "SELECT outstanding_balance_cents FROM member_finance_accounts WHERE member_id=%s",
        (member,),
    )
    assert (
        cursor.fetchone()["outstanding_balance_cents"]
        == BalanceEngine(sb_client).member_outstanding(member).cents
    )


async def test_partial_status_with_zero_remaining_does_not_count(
    api, sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    _make_required_event(cursor, chapter_id)
    cursor.execute(
        "INSERT INTO unpaid_invoices (chapter_id,member_id,kind,amount_cents,status) VALUES (%s,%s,'fine',2500,'partially_paid') RETURNING id",
        (chapter_id, member),
    )
    invoice = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id,member_id,amount_cents) VALUES (%s,%s,2500) RETURNING id",
        (chapter_id, member),
    )
    payment = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO payment_allocations (chapter_id,verified_payment_id,invoice_id,amount_cents) VALUES (%s,%s,%s,2500)",
        (chapter_id, payment, invoice),
    )
    row = _row_for(await load_member_engagement(chapter_id), member)
    assert (row.unpaid_fines, row.unpaid_amount_cents) == (0, 0)


def test_excuse_review_survives_cache_failure(
    api, sb_client, cursor, chapter_id, member_factory, monkeypatch, caplog
):
    from tests.treasury.test_v1_helpers import make_user
    from api.treasury.core.balance import BalanceEngine

    officer = member_factory(role="officer")
    member = member_factory()
    event = _make_required_event(cursor, chapter_id)
    cursor.execute(
        "INSERT INTO excuses (chapter_id,event_id,member_id,reason) VALUES (%s,%s,%s,'test') RETURNING id",
        (chapter_id, event, member),
    )
    excuse = str(cursor.fetchone()["id"])

    def fail_refresh(self, member_id):
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr(BalanceEngine, "recompute_member", fail_refresh)
    response = api(make_user(officer, chapter_id, "officer")).put(
        f"/api/excuses/{excuse}/review",
        json={"status": "approved"},
        headers={"Authorization": "Bearer x"},
    )
    assert response.status_code == 200, response.text
    cursor.execute("SELECT status FROM excuses WHERE id=%s", (excuse,))
    assert cursor.fetchone()["status"] == "approved"
    assert "Failed to refresh balance after excuse review" in caplog.text
