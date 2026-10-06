"""Dues run (#50/#45) — the two additive backend bits the greekos money loop needs.

1. tr_bulk_create_invoices carries a per-item due_at and stamps issued_by (0158),
   so a dues run's invoices can say when they are due.
2. list_payment_submissions attaches evidence metadata, so the officer verify
   queue can open the proof a member attached without a second round trip per row.
"""

from __future__ import annotations

import uuid

from api.platform.rpc import call_rpc
from api.treasury.services.reports import list_payment_submissions
from tests.treasury.test_v1_helpers import api, assign_role, make_user  # noqa: F401


def test_bulk_create_carries_due_at_and_issued_by(sb_client, cursor, chapter_id, member_factory):
    officer = member_factory(role="officer")
    a, b = member_factory(), member_factory()
    due = "2026-10-01T00:00:00+00:00"

    result = call_rpc(
        "tr_bulk_create_invoices",
        {
            "p_chapter_id": chapter_id,
            "p_invoices": [
                {"member_id": a, "kind": "dues", "amount_cents": 25000,
                 "description": "Fall 2026 dues", "due_at": due},
                {"member_id": b, "kind": "dues", "amount_cents": 25000,
                 "description": "Fall 2026 dues", "due_at": due},
            ],
            "p_actor_id": officer,
        },
        sb=sb_client,
    ).data

    assert result["count"] == 2

    cursor.execute(
        "SELECT due_at, issued_by, description FROM unpaid_invoices WHERE chapter_id = %s",
        (chapter_id,),
    )
    rows = cursor.fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["due_at"] is not None
        assert row["due_at"].isoformat() == due
        assert str(row["issued_by"]) == officer
        assert row["description"] == "Fall 2026 dues"


def test_bulk_create_without_due_at_still_works(sb_client, cursor, chapter_id, member_factory):
    """Additive: the pre-0158 payload shape keeps working, due_at stays NULL."""
    officer = member_factory(role="officer")
    member = member_factory()

    result = call_rpc(
        "tr_bulk_create_invoices",
        {
            "p_chapter_id": chapter_id,
            "p_invoices": [{"member_id": member, "kind": "dues", "amount_cents": 1000}],
            "p_actor_id": officer,
        },
        sb=sb_client,
    ).data

    assert result["count"] == 1
    cursor.execute("SELECT due_at FROM unpaid_invoices WHERE chapter_id = %s", (chapter_id,))
    assert cursor.fetchone()["due_at"] is None


# ── F-070 / D11: a reused dues-run key with a different payload is rejected ───
def _dues_run(api, officer, chapter_id, member, amount, key):
    return api(make_user(officer, chapter_id)).post(
        "/api/treasury/invoices/bulk",
        json={"invoices": [{"member_id": member, "kind": "dues", "amount_cents": amount}]},
        headers={"Authorization": "Bearer x", "Idempotency-Key": key},
    )


def test_same_key_different_items_is_rejected(api, cursor, chapter_id, member_factory):
    officer, member = member_factory(), member_factory()
    assign_role(cursor, chapter_id, officer, "treasurer")
    key = f"dues-{uuid.uuid4()}"

    assert _dues_run(api, officer, chapter_id, member, 10000, key).status_code == 200
    resp = _dues_run(api, officer, chapter_id, member, 12000, key)

    assert resp.status_code == 409, resp.text
    cursor.execute("SELECT amount_cents FROM unpaid_invoices WHERE chapter_id = %s", (chapter_id,))
    assert [r["amount_cents"] for r in cursor.fetchall()] == [10000]


def test_same_key_same_items_replays(api, cursor, chapter_id, member_factory):
    officer, member = member_factory(), member_factory()
    assign_role(cursor, chapter_id, officer, "treasurer")
    key = f"dues-{uuid.uuid4()}"

    first = _dues_run(api, officer, chapter_id, member, 10000, key)
    second = _dues_run(api, officer, chapter_id, member, 10000, key)

    assert second.status_code == 200
    assert second.json() == first.json()
    cursor.execute("SELECT count(*) AS n FROM unpaid_invoices WHERE chapter_id = %s", (chapter_id,))
    assert cursor.fetchone()["n"] == 1


def test_review_queue_rows_carry_evidence_metadata(sb_client, cursor, chapter_id, member_id):
    cursor.execute(
        """
        INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
        VALUES (%s, %s, 'dues', 5000, 'unpaid') RETURNING id
        """,
        (chapter_id, member_id),
    )
    invoice_id = str(cursor.fetchone()["id"])
    cursor.execute(
        """
        INSERT INTO payment_submissions
            (chapter_id, member_id, invoice_id, claimed_amount_cents, method, status)
        VALUES (%s, %s, %s, 5000, 'venmo', 'pending') RETURNING id
        """,
        (chapter_id, member_id, invoice_id),
    )
    submission_id = str(cursor.fetchone()["id"])
    cursor.execute(
        """
        INSERT INTO payment_evidence (chapter_id, submission_id, content_type, data, size_bytes)
        VALUES (%s, %s, 'image/png', %s, 4) RETURNING id
        """,
        (chapter_id, submission_id, psycopg2_bytes(b"abcd")),
    )
    evidence_id = str(cursor.fetchone()["id"])

    page = list_payment_submissions(sb_client, chapter_id=chapter_id)
    row = next(r for r in page["data"] if str(r["id"]) == submission_id)

    assert [str(e["id"]) for e in row["evidence"]] == [evidence_id]
    assert row["evidence"][0]["content_type"] == "image/png"
    # The bytes never travel in the queue payload.
    assert "data" not in row["evidence"][0]


def test_review_queue_row_without_evidence_gets_empty_list(sb_client, cursor, chapter_id, member_id):
    cursor.execute(
        """
        INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
        VALUES (%s, %s, 'dues', 5000, 'unpaid') RETURNING id
        """,
        (chapter_id, member_id),
    )
    invoice_id = str(cursor.fetchone()["id"])
    cursor.execute(
        """
        INSERT INTO payment_submissions
            (chapter_id, member_id, invoice_id, claimed_amount_cents, method, status)
        VALUES (%s, %s, %s, 5000, 'cash', 'pending') RETURNING id
        """,
        (chapter_id, member_id, invoice_id),
    )
    submission_id = str(cursor.fetchone()["id"])

    page = list_payment_submissions(sb_client, chapter_id=chapter_id)
    row = next(r for r in page["data"] if str(r["id"]) == submission_id)
    assert row["evidence"] == []


def psycopg2_bytes(data: bytes):
    import psycopg2

    return psycopg2.Binary(data)
