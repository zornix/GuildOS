"""Chunk H — Tenant-integrity guards (security hardening).

The money-moving RPCs run as the service-role client, which BYPASSES RLS. A
body-supplied member_id or invoice_id is therefore only as trustworthy as the
checks inside the RPC. These tests pin the invariant that an operation can never
attribute debt/credit to a member outside the caller's chapter, and that a member
cannot submit a payment proof against another member's invoice.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from api.treasury.services import adjustments as adj_svc
from api.treasury.services import invoices as svc


@pytest.fixture(autouse=True)
def _stub_recompute(monkeypatch):
    # Guards raise before any recompute; stub keeps the BalanceEngine out of the way
    # for the valid-path regression test below.
    monkeypatch.setattr(svc, "recompute_member_balance", lambda sb, member_id: None)


@pytest.fixture
def other_chapter(cursor) -> str:
    cursor.execute(
        """
        INSERT INTO chapters (name, organization, school)
        VALUES (%s, 'Treasury Test Org', 'Test University')
        RETURNING id
        """,
        (f"tr-test-other-{uuid.uuid4()}",),
    )
    return str(cursor.fetchone()["id"])


# ── invoices: member must belong to the chapter ──────────────────────────────
def test_create_invoice_rejects_member_from_another_chapter(
    sb_client, chapter_id, other_chapter, member_factory
):
    foreign_member = member_factory(chapter=other_chapter)
    with pytest.raises(Exception):
        svc.create_invoice(
            sb_client, chapter_id=chapter_id, member_id=foreign_member, kind="dues",
            amount_cents=5000, description=None, actor_id=foreign_member,
        )


def test_bulk_create_invoices_rejects_foreign_member_atomically(
    sb_client, cursor, chapter_id, other_chapter, member_factory
):
    local_member = member_factory()
    foreign_member = member_factory(chapter=other_chapter)
    with pytest.raises(Exception):
        svc.bulk_create_invoices(
            sb_client,
            chapter_id=chapter_id,
            invoices=[
                {"member_id": local_member, "kind": "dues", "amount_cents": 5000, "description": None},
                {"member_id": foreign_member, "kind": "dues", "amount_cents": 5000, "description": None},
            ],
            actor_id=local_member,
        )
    # Atomic: the valid first row must NOT have been committed.
    cursor.execute(
        "SELECT COUNT(*) AS n FROM unpaid_invoices WHERE chapter_id = %s AND member_id = %s",
        (chapter_id, local_member),
    )
    assert cursor.fetchone()["n"] == 0


# ── adjustments: member-scoped must belong to the chapter; chapter-level allowed ─
def test_create_adjustment_rejects_member_from_another_chapter(
    sb_client, chapter_id, other_chapter, member_factory
):
    foreign_member = member_factory(chapter=other_chapter)
    with pytest.raises(Exception):
        adj_svc.create_adjustment(
            sb_client, chapter_id=chapter_id, member_id=foreign_member,
            kind="manual_correction", delta_cents=-1000, reason="x", officer_id=foreign_member,
        )


def test_create_adjustment_allows_chapter_level_null_member(
    sb_client, chapter_id, member_factory
):
    officer = member_factory(role="officer")
    adj = adj_svc.create_adjustment(
        sb_client, chapter_id=chapter_id, member_id=None,
        kind="manual_correction", delta_cents=-1000, reason="chapter writeoff",
        officer_id=officer,
    )
    assert adj["member_id"] is None
    assert adj["status"] == "active"


# ── submissions: the invoice must belong to the submitting member ────────────
def test_submit_payment_rejects_another_members_invoice(
    sb_client, chapter_id, member_factory
):
    member_a = member_factory()
    member_b = member_factory()
    invoice_b = svc.create_invoice(
        sb_client, chapter_id=chapter_id, member_id=member_b, kind="dues",
        amount_cents=5000, description=None, actor_id=member_b,
    )
    with pytest.raises(Exception):
        svc.submit_payment(
            sb_client, chapter_id=chapter_id, member_id=member_a,
            invoice_id=invoice_b["id"], claimed_amount_cents=5000, method="venmo",
            proof_ref=None, actor_id=member_a,
        )


# ── balance read endpoint: capability + same-chapter (read-side guard) ───────
# GET /members/{id}/balance previously let any role=="officer" read ANY member's
# balance, including across chapters. The hardened guard (mirroring /statement)
# requires the member themself OR a same-chapter treasury:read holder, and 404s
# anything outside the caller's chapter so cross-chapter existence never leaks.
# The endpoint reads `sb` from get_treasury_db(); we point it at the test client
# and call the handler directly with a plain user dict (no FastAPI Depends).


def _grant(cursor, chapter, member, capability):
    cursor.execute(
        "INSERT INTO treasury_grants (chapter_id, member_id, capability) VALUES (%s, %s, %s)",
        (chapter, member, capability),
    )


async def test_balance_self_read_allowed(
    sb_client, monkeypatch, chapter_id, member_factory
):
    from api.treasury.api import balances

    monkeypatch.setattr(balances, "get_treasury_db", lambda: sb_client)
    member = member_factory()
    result = await balances.get_member_balance(
        member, user={"id": member, "chapter_id": chapter_id}
    )
    assert result["member_id"] == member


async def test_balance_read_requires_capability(
    sb_client, monkeypatch, chapter_id, member_factory
):
    from api.treasury.api import balances

    monkeypatch.setattr(balances, "get_treasury_db", lambda: sb_client)
    target = member_factory()
    requester = member_factory(role="officer")  # role alone no longer grants access
    with pytest.raises(HTTPException) as exc:
        await balances.get_member_balance(
            target, user={"id": requester, "chapter_id": chapter_id}
        )
    assert exc.value.status_code == 403


async def test_balance_read_allowed_for_same_chapter_treasury_read(
    sb_client, cursor, monkeypatch, chapter_id, member_factory
):
    from api.treasury.api import balances

    monkeypatch.setattr(balances, "get_treasury_db", lambda: sb_client)
    target = member_factory()
    requester = member_factory()
    _grant(cursor, chapter_id, requester, "treasury:read")
    result = await balances.get_member_balance(
        target, user={"id": requester, "chapter_id": chapter_id}
    )
    assert result["member_id"] == target


async def test_balance_read_404s_member_in_another_chapter(
    sb_client, cursor, monkeypatch, chapter_id, other_chapter, member_factory
):
    from api.treasury.api import balances

    monkeypatch.setattr(balances, "get_treasury_db", lambda: sb_client)
    foreign_target = member_factory(chapter=other_chapter)
    requester = member_factory()
    _grant(cursor, chapter_id, requester, "treasury:read")  # holds the cap in their OWN chapter
    with pytest.raises(HTTPException) as exc:
        await balances.get_member_balance(
            foreign_target, user={"id": requester, "chapter_id": chapter_id}
        )
    assert exc.value.status_code == 404
