import csv
import io

from api.treasury.core.balance import BalanceEngine
from api.treasury.services.reports import (
    dashboard_summary,
    period_report_csv,
    member_statement,
)


def _invoice(cursor, chapter, member, amount):
    cursor.execute(
        "INSERT INTO unpaid_invoices (chapter_id,member_id,kind,amount_cents) VALUES (%s,%s,'dues',%s)",
        (chapter, member, amount),
    )


def _payment(cursor, chapter, member, amount, submission=None):
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id,member_id,amount_cents,submission_id) VALUES (%s,%s,%s,%s) RETURNING id",
        (chapter, member, amount, submission),
    )
    return str(cursor.fetchone()["id"])


def test_bulk_matches_member_formula(sb_client, cursor, chapter_id, member_factory):
    members = [member_factory() for _ in range(4)]
    for member, owed, paid in zip(
        members, (10000, 10000, 5000, 5000), (0, 4000, 9000, 5000)
    ):
        _invoice(cursor, chapter_id, member, owed)
        if paid:
            payment = _payment(cursor, chapter_id, member, paid)
    cursor.execute(
        "INSERT INTO refunds (chapter_id,member_id,verified_payment_id,amount_cents,reason,officer_id) VALUES (%s,%s,%s,5000,'test',%s)",
        (chapter_id, members[3], payment, members[0]),
    )
    cursor.execute(
        "INSERT INTO finance_adjustments (chapter_id,member_id,delta_cents,kind,reason,officer_id) VALUES (%s,%s,-1000,'manual_correction','test',%s)",
        (chapter_id, members[3], members[0]),
    )
    engine = BalanceEngine(sb_client)
    outstanding = engine.outstanding_by_member(chapter_id)
    assert [outstanding[m] for m in members] == [10000, 6000, 0, 4000]
    assert all(outstanding[m] == engine.member_outstanding(m).cents for m in members)


def test_dashboard_counts_a_fine_the_cache_never_saw(
    sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    cursor.execute(
        "INSERT INTO unpaid_invoices (chapter_id,member_id,kind,amount_cents) VALUES (%s,%s,'fine',2500)",
        (chapter_id, member),
    )
    dashboard = dashboard_summary(sb_client, chapter_id=chapter_id)
    assert dashboard["total_outstanding_cents"] == 2500
    assert dashboard["members_with_balance_count"] == 1


def test_export_includes_uncached_and_stale_members(
    sb_client, cursor, chapter_id, member_factory
):
    a, b = member_factory(), member_factory()
    _invoice(cursor, chapter_id, a, 10000)
    BalanceEngine(sb_client).recompute_member(a)
    _payment(cursor, chapter_id, a, 4000)
    _invoice(cursor, chapter_id, b, 2500)
    rows = list(
        csv.DictReader(
            io.StringIO(
                period_report_csv(
                    sb_client,
                    chapter_id=chapter_id,
                    period="2026-10",
                    dataset="member_balances",
                )
            )
        )
    )
    assert {r["member_id"]: int(r["outstanding_balance_cents"]) for r in rows} == {
        a: 6000,
        b: 2500,
    }


def test_recent_payment_includes_submission_method(
    sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    cursor.execute(
        "INSERT INTO payment_submissions (chapter_id,member_id,claimed_amount_cents,method) VALUES (%s,%s,100,'cash') RETURNING id",
        (chapter_id, member),
    )
    submission = str(cursor.fetchone()["id"])
    _payment(cursor, chapter_id, member, 100, submission)
    assert (
        dashboard_summary(sb_client, chapter_id=chapter_id)["recent_payments"][0][
            "method"
        ]
        == "cash"
    )


def test_statement_payment_has_no_obsolete_invoice_attribution(
    sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    _payment(cursor, chapter_id, member, 100)
    entry = member_statement(sb_client, member_id=member)["entries"][0]
    assert "invoice_id" not in entry["detail"]


def test_balance_audiences_use_live_figures(
    sb_client, cursor, chapter_id, member_factory, monkeypatch
):
    from api.announcements.services.sms import resolve_recipients
    from api.announcements.services.announcements import audiences_for_viewer

    monkeypatch.setattr(
        "api.announcements.services.sms.delivery_mode", lambda: "dry_run"
    )
    member = member_factory()
    cursor.execute("UPDATE members SET phone='+15555550123' WHERE id=%s", (member,))
    _invoice(cursor, chapter_id, member, 2500)
    assert resolve_recipients(
        sb_client, chapter_id=chapter_id, audience="members_with_balance"
    )["recipient_member_ids"] == [member]
    assert "members_with_balance" in audiences_for_viewer(
        sb_client, chapter_id=chapter_id, viewer={"id": member, "role": "member"}
    )
