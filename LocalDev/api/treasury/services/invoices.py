"""Receivables service — invoices, payment submissions, cancellation, bulk.

Every multi-write operation is delegated to a `tr_*` plpgsql RPC (the only atomic
path). Reads use the `sb.table(...)` builder.
"""

from __future__ import annotations

from typing import Any

from api.treasury.core.idempotency import idempotency_operation  # noqa: F401  (contract anchor)
from api.treasury.db.rpc import call_rpc
from api.treasury.notifications import notify_invoice_issued


# ── single recompute call site (CHUNK A→B/C handoff) ─────────────────────────
def recompute_member_balance(sb, member_id: str) -> None:
    """The ONE place receivables refreshes a member's cached balance.

    `BalanceEngine.recompute_member` writes only the `member_finance_accounts`
    cache. Payment verification (Chunk C) refreshes through this same call site.
    Keep this the only recompute call in the receivables service.
    """
    from api.treasury.core.balance import BalanceEngine

    BalanceEngine(sb).recompute_member(member_id)


def _row(result: Any) -> dict:
    data = result.data
    if isinstance(data, list):
        return data[0]
    return data


def create_invoice(
    sb,
    *,
    chapter_id: str,
    member_id: str,
    kind: str,
    amount_cents: int,
    description: str | None,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tr_create_invoice",
        {
            "p_chapter_id": chapter_id,
            "p_member_id": member_id,
            "p_kind": kind,
            "p_amount_cents": amount_cents,
            "p_description": description,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    invoice = result.data
    recompute_member_balance(sb, member_id)
    # Exactly-once on retry: the outbox dedups on the invoice id, so an idempotent
    # replay (same invoice returned) enqueues no second notification.
    notify_invoice_issued(
        chapter_id=chapter_id, member_id=member_id, invoice_id=invoice["id"], sb=sb
    )
    return invoice


def submit_payment(
    sb,
    *,
    chapter_id: str,
    member_id: str,
    invoice_id: str,
    claimed_amount_cents: int,
    method: str,
    proof_ref: str | None,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    # No money moves on submission — no recompute, no ledger (Slice 2 / invariant 5).
    result = call_rpc(
        "tr_submit_payment",
        {
            "p_chapter_id": chapter_id,
            "p_member_id": member_id,
            "p_invoice_id": invoice_id,
            "p_claimed_amount_cents": claimed_amount_cents,
            "p_method": method,
            "p_proof_ref": proof_ref,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def cancel_invoice(
    sb,
    *,
    chapter_id: str,
    invoice_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tr_cancel_invoice",
        {
            "p_chapter_id": chapter_id,
            "p_invoice_id": invoice_id,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    invoice = result.data
    recompute_member_balance(sb, invoice["member_id"])
    return invoice


def bulk_create_invoices(
    sb,
    *,
    chapter_id: str,
    invoices: list[dict],
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tr_bulk_create_invoices",
        {
            "p_chapter_id": chapter_id,
            "p_invoices": invoices,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    payload = result.data
    for member_id in {inv["member_id"] for inv in invoices}:
        recompute_member_balance(sb, member_id)
    return payload
