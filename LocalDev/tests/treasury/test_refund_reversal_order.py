"""Review regressions: refund coverage follows cancelled credit first."""

import uuid

import psycopg2
import pytest


def test_refund_reverses_cancelled_allocation_before_paid(cursor, chapter_id, member_id):
    invoices = []
    for status in ("paid", "cancelled"):
        cursor.execute(
            "INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status) "
            "VALUES (%s, %s, 'dues', 3000, %s) RETURNING id",
            (chapter_id, member_id, status),
        )
        invoices.append(str(cursor.fetchone()["id"]))
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id, member_id, amount_cents, verified_by) "
        "VALUES (%s, %s, 6000, %s) RETURNING id",
        (chapter_id, member_id, member_id),
    )
    payment = str(cursor.fetchone()["id"])
    # The paid allocation sorts first under the old UUID tiebreaker. Both
    # allocations receive exactly the same timestamp in this single statement.
    cancelled_allocation, paid_allocation = sorted(str(uuid.uuid4()) for _ in range(2))
    cursor.execute(
        "INSERT INTO payment_allocations "
        "(id, chapter_id, verified_payment_id, invoice_id, amount_cents) "
        "VALUES (%s, %s, %s, %s, 3000), (%s, %s, %s, %s, 3000)",
        (paid_allocation, chapter_id, payment, invoices[0],
         cancelled_allocation, chapter_id, payment, invoices[1]),
    )
    cursor.execute(
        "SELECT tr_issue_refund(%s, %s, 3000, 'return credit', %s)",
        (chapter_id, payment, member_id),
    )
    cursor.execute("SELECT status FROM unpaid_invoices WHERE chapter_id=%s AND id=%s",
                   (chapter_id, invoices[0]))
    assert cursor.fetchone()["status"] == "paid"
    cursor.execute(
        "SELECT invoice_id, reverses_allocation_id FROM payment_allocations "
        "WHERE chapter_id=%s AND verified_payment_id=%s AND reverses_allocation_id IS NOT NULL",
        (chapter_id, payment),
    )
    reversals = cursor.fetchall()
    assert [(str(r["invoice_id"]), str(r["reverses_allocation_id"])) for r in reversals] == [
        (invoices[1], cancelled_allocation)
    ]


def test_refund_reverses_newer_paid_invoice_first(cursor, chapter_id, member_id):
    """Same-now() allocations: the newest invoice reopens, not a uuid coin flip."""
    invoices = []
    for days_ago in (10, 1):  # older first, newer second
        cursor.execute(
            "INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status, created_at) "
            "VALUES (%s, %s, 'dues', 3000, 'paid', now() - make_interval(days => %s)) RETURNING id",
            (chapter_id, member_id, days_ago),
        )
        invoices.append(str(cursor.fetchone()["id"]))
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id, member_id, amount_cents, verified_by) "
        "VALUES (%s, %s, 6000, %s) RETURNING id",
        (chapter_id, member_id, member_id),
    )
    payment = str(cursor.fetchone()["id"])
    # Adversarial uuids: the OLDER invoice's allocation gets the larger pa.id,
    # so the old pa.id tiebreak would reverse the older invoice first.
    newer_allocation, older_allocation = sorted(str(uuid.uuid4()) for _ in range(2))
    cursor.execute(
        "INSERT INTO payment_allocations "
        "(id, chapter_id, verified_payment_id, invoice_id, amount_cents) "
        "VALUES (%s, %s, %s, %s, 3000), (%s, %s, %s, %s, 3000)",
        (older_allocation, chapter_id, payment, invoices[0],
         newer_allocation, chapter_id, payment, invoices[1]),
    )
    cursor.execute(
        "SELECT tr_issue_refund(%s, %s, 3000, 'return credit', %s)",
        (chapter_id, payment, member_id),
    )
    cursor.execute("SELECT status FROM unpaid_invoices WHERE chapter_id=%s AND id=%s",
                   (chapter_id, invoices[0]))
    assert cursor.fetchone()["status"] == "paid"
    cursor.execute(
        "SELECT reverses_allocation_id FROM payment_allocations "
        "WHERE chapter_id=%s AND verified_payment_id=%s AND reverses_allocation_id IS NOT NULL",
        (chapter_id, payment),
    )
    assert [str(r["reverses_allocation_id"]) for r in cursor.fetchall()] == [newer_allocation]


def test_refund_member_is_frozen(cursor, chapter_id, member_id, member_factory):
    other = member_factory()
    cursor.execute(
        "INSERT INTO verified_payments (chapter_id, member_id, amount_cents, verified_by) "
        "VALUES (%s, %s, 3000, %s) RETURNING id",
        (chapter_id, member_id, member_id),
    )
    payment = str(cursor.fetchone()["id"])
    cursor.execute(
        "SELECT tr_issue_refund(%s, %s, 1000, 'return credit', %s) AS result",
        (chapter_id, payment, member_id),
    )
    refund = cursor.fetchone()["result"]["id"]
    with pytest.raises(psycopg2.Error, match=r"frozen: refunds.member_id"):
        cursor.execute("UPDATE refunds SET member_id=%s WHERE chapter_id=%s AND id=%s",
                       (other, chapter_id, refund))
    cursor.execute("SELECT member_id FROM refunds WHERE chapter_id=%s AND id=%s", (chapter_id, refund))
    assert str(cursor.fetchone()["member_id"]) == member_id
