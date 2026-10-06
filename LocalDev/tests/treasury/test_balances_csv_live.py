import csv
import io

import pytest

from api.treasury.core.balance import BalanceEngine
from api.treasury.services.reports import dashboard_summary, period_report_csv


@pytest.mark.parametrize("cache", ["missing", "stale"])
def test_all_balance_columns_are_live(
    sb_client, cursor, chapter_id, member_factory, cache
):
    member = member_factory()
    cursor.execute(
        "INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents) "
        "VALUES (%s, %s, 'dues', 10000)", (chapter_id, member),
    )
    if cache == "stale":
        BalanceEngine(sb_client).recompute_member(member)
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id, member_id, amount_cents) "
        "VALUES (%s, %s, 4000)", (chapter_id, member),
    )
    if cache == "missing":
        cursor.execute("DELETE FROM member_finance_accounts WHERE member_id=%s", (member,))
    rows = list(csv.DictReader(io.StringIO(period_report_csv(
        sb_client, chapter_id=chapter_id, period="2026-10", dataset="member_balances"
    ))))
    row = next(r for r in rows if r["member_id"] == member)
    assert row["total_owed_cents"] == "10000"
    assert row["total_paid_cents"] == "4000"
    assert row["current_balance_cents"] == "6000"
    assert row["outstanding_balance_cents"] == "6000"
    assert "recomputed_at" not in row


def test_recent_payments_include_submission_reference(
    sb_client, cursor, chapter_id, member_factory
):
    member = member_factory()
    cursor.execute(
        "INSERT INTO payment_submissions "
        "(chapter_id, member_id, claimed_amount_cents, method, proof_ref) "
        "VALUES (%s, %s, 100, 'cash', 'receipt-example') RETURNING id",
        (chapter_id, member),
    )
    submission = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id, member_id, amount_cents, submission_id) "
        "VALUES (%s, %s, 100, %s)", (chapter_id, member, submission),
    )
    row = dashboard_summary(sb_client, chapter_id=chapter_id)["recent_payments"][0]
    assert row.get("proof_ref") == "receipt-example"
    assert row["method"] == "cash"


def test_csv_matches_balance_formula_for_credit_refunds_and_adjustments(
    sb_client, cursor, chapter_id, member_factory
):
    member, empty = member_factory(), member_factory()
    cursor.execute(
        "INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status) "
        "VALUES (%s, %s, 'dues', 5000, 'unpaid'), (%s, %s, 'dues', 9000, 'cancelled')",
        (chapter_id, member, chapter_id, member),
    )
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id, member_id, amount_cents) "
        "VALUES (%s, %s, 7000) RETURNING id", (chapter_id, member),
    )
    payment = str(cursor.fetchone()["id"])
    cursor.execute(
        "INSERT INTO refunds "
        "(chapter_id, member_id, verified_payment_id, amount_cents, reason, officer_id) "
        "VALUES (%s, %s, %s, 1000, 'test', %s)",
        (chapter_id, member, payment, member),
    )
    for target, delta, status in [(member, -500, "active"), (member, 2000, "pending"), (None, 800, "active")]:
        cursor.execute(
            "INSERT INTO finance_adjustments "
            "(chapter_id, member_id, delta_cents, kind, reason, officer_id, status) "
            "VALUES (%s, %s, %s, 'manual_correction', 'test', %s, %s)",
            (chapter_id, target, delta, member, status),
        )
    rows = list(csv.DictReader(io.StringIO(period_report_csv(
        sb_client, chapter_id=chapter_id, period="2026-10", dataset="member_balances"
    ))))
    assert {r["member_id"] for r in rows} == {member, empty}
    engine = BalanceEngine(sb_client)
    for row in rows:
        figures = engine._member_figures(row["member_id"])
        assert row["chapter_id"] == chapter_id
        for column in ("total_owed_cents", "total_paid_cents", "current_balance_cents", "outstanding_balance_cents"):
            assert int(row[column]) == figures[column]
    credit = next(r for r in rows if r["member_id"] == member)
    assert credit["current_balance_cents"] == "-1500"
    assert credit["outstanding_balance_cents"] == "0"
