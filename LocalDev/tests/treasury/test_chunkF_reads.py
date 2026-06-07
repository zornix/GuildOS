"""Chunk F-partial — Review Queue service tests.

Tests for list_payment_submissions in api/treasury/services/reports.py.
All assertions are chapter-scoped (see conftest §3.4): only rows belonging
to the fixture chapter_id are inspected, never global counts.
"""

from __future__ import annotations

import uuid

import pytest

from api.treasury.services.reports import list_payment_submissions


# ── helpers ──────────────────────────────────────────────────────────────────

def _insert_invoice(cursor, chapter_id: str, member_id: str) -> str:
    """Insert an unpaid_invoice row directly and return its id."""
    cursor.execute(
        """
        INSERT INTO unpaid_invoices (chapter_id, member_id, kind, amount_cents, status)
        VALUES (%s, %s, 'dues', 5000, 'unpaid')
        RETURNING id
        """,
        (chapter_id, member_id),
    )
    return str(cursor.fetchone()["id"])


def _insert_submission(
    cursor,
    chapter_id: str,
    member_id: str,
    invoice_id: str,
    *,
    status: str = "pending",
    method: str = "venmo",
    claimed_amount_cents: int = 5000,
) -> str:
    """Insert a payment_submission directly and return its id."""
    cursor.execute(
        """
        INSERT INTO payment_submissions
            (chapter_id, member_id, invoice_id, claimed_amount_cents, method, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (chapter_id, member_id, invoice_id, claimed_amount_cents, method, status),
    )
    return str(cursor.fetchone()["id"])


# ── Test 1: chapter isolation + status filtering ──────────────────────────────

def test_queue_returns_only_pending_for_own_chapter(
    sb_client, cursor, chapter_id, member_id, member_factory
):
    """Only pending submissions for the caller's chapter are returned.

    Setup:
      - 2 pending submissions in the test chapter
      - 1 approved submission in the test chapter   → excluded (wrong status)
      - 1 pending submission in a DIFFERENT chapter → excluded (wrong chapter)
    """
    invoice_a = _insert_invoice(cursor, chapter_id, member_id)
    invoice_b = _insert_invoice(cursor, chapter_id, member_id)
    invoice_c = _insert_invoice(cursor, chapter_id, member_id)

    sub_pending_1 = _insert_submission(cursor, chapter_id, member_id, invoice_a, status="pending")
    sub_pending_2 = _insert_submission(cursor, chapter_id, member_id, invoice_b, status="pending")
    _insert_submission(cursor, chapter_id, member_id, invoice_c, status="approved")  # excluded

    # Different chapter + member
    other_chapter_id = _make_chapter(cursor)
    other_member_id = _make_member(cursor, other_chapter_id)
    other_invoice = _insert_invoice(cursor, other_chapter_id, other_member_id)
    _insert_submission(cursor, other_chapter_id, other_member_id, other_invoice, status="pending")  # excluded

    result = list_payment_submissions(sb_client, chapter_id=chapter_id, status="pending")

    returned_ids = {row["id"] for row in result["data"]}
    assert sub_pending_1 in returned_ids
    assert sub_pending_2 in returned_ids
    # Must NOT include the approved row or the other-chapter row
    assert all(row["chapter_id"] == chapter_id for row in result["data"])
    assert all(row["status"] == "pending" for row in result["data"])


# ── Test 2: pagination envelope ───────────────────────────────────────────────

def test_pagination_envelope_shape_and_next_cursor(
    sb_client, cursor, chapter_id, member_id
):
    """Envelope has data/next_cursor/total; paging through limit<total reaches all rows."""
    # Insert 5 pending submissions
    sub_ids = set()
    for _ in range(5):
        inv = _insert_invoice(cursor, chapter_id, member_id)
        sid = _insert_submission(cursor, chapter_id, member_id, inv, status="pending")
        sub_ids.add(sid)

    # Page 1 — limit 2
    page1 = list_payment_submissions(sb_client, chapter_id=chapter_id, status="pending", limit=2, offset=0)
    assert "data" in page1
    assert "next_cursor" in page1
    assert "total" in page1

    assert page1["total"] >= 5  # could be more from other tests, scoped to chapter
    assert len(page1["data"]) == 2
    assert page1["next_cursor"] is not None  # more rows remain

    # Collect all via cursor-walking
    collected = list(page1["data"])
    offset = int(page1["next_cursor"])
    while True:
        page = list_payment_submissions(
            sb_client, chapter_id=chapter_id, status="pending", limit=2, offset=offset
        )
        collected.extend(page["data"])
        if page["next_cursor"] is None:
            break
        offset = int(page["next_cursor"])

    collected_ids = {row["id"] for row in collected}
    assert sub_ids.issubset(collected_ids)


# ── Test 3: filter by member_id ───────────────────────────────────────────────

def test_filter_by_member_id(sb_client, cursor, chapter_id, member_factory):
    """Passing member_id returns only that member's submissions."""
    m1 = member_factory()
    m2 = member_factory()

    inv1 = _insert_invoice(cursor, chapter_id, m1)
    inv2 = _insert_invoice(cursor, chapter_id, m2)
    sub1 = _insert_submission(cursor, chapter_id, m1, inv1, status="pending")
    _insert_submission(cursor, chapter_id, m2, inv2, status="pending")  # different member

    result = list_payment_submissions(sb_client, chapter_id=chapter_id, status="pending", member_id=m1)

    assert len(result["data"]) >= 1
    assert all(row["member_id"] == m1 for row in result["data"])
    returned_ids = {row["id"] for row in result["data"]}
    assert sub1 in returned_ids


# ── Test 4: filter by method ──────────────────────────────────────────────────

def test_filter_by_method(sb_client, cursor, chapter_id, member_id):
    """Passing method returns only submissions with that payment method."""
    inv_venmo = _insert_invoice(cursor, chapter_id, member_id)
    inv_zelle = _insert_invoice(cursor, chapter_id, member_id)

    sub_venmo = _insert_submission(cursor, chapter_id, member_id, inv_venmo, method="venmo", status="pending")
    _insert_submission(cursor, chapter_id, member_id, inv_zelle, method="zelle", status="pending")

    result = list_payment_submissions(
        sb_client, chapter_id=chapter_id, status="pending", method="venmo"
    )

    assert len(result["data"]) >= 1
    assert all(row["method"] == "venmo" for row in result["data"])
    returned_ids = {row["id"] for row in result["data"]}
    assert sub_venmo in returned_ids


# ── helpers (not fixtures — called inline) ────────────────────────────────────

def _make_chapter(cursor) -> str:
    cursor.execute(
        """
        INSERT INTO chapters (name, organization, school)
        VALUES (%s, 'Other Org', 'Other University')
        RETURNING id
        """,
        (f"other-{uuid.uuid4()}",),
    )
    return str(cursor.fetchone()["id"])


def _make_member(cursor, chapter_id: str) -> str:
    cursor.execute(
        """
        INSERT INTO members (chapter_id, name, email, role, status)
        VALUES (%s, %s, %s, 'member', 'active')
        RETURNING id
        """,
        (chapter_id, f"M-{uuid.uuid4().hex[:8]}", f"{uuid.uuid4()}@other.local"),
    )
    return str(cursor.fetchone()["id"])
