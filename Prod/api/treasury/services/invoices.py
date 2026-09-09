"""Receivables service — invoices, payment submissions, cancellation, bulk.

Every multi-write operation is delegated to a `tr_*` plpgsql RPC (the only atomic
path). Reads use the `sb.table(...)` builder.
"""

from __future__ import annotations


from api.treasury.core.idempotency import idempotency_operation  # noqa: F401  (contract anchor)
from api.platform.rpc import call_rpc
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


def create_invoice_v2(
    sb,
    *,
    chapter_id: str,
    member_id: str,
    kind: str,
    amount_cents: int,
    description: str | None,
    actor_id: str,
    due_at: str | None = None,
    issued_by: str | None = None,
    line_items: list[dict] | None = None,
    idempotency_key: str | None = None,
    source_event_id: str | None = None,
) -> dict:
    """V1 invoice creation: due_at + issued_by + optional line items.

    Delegates to tr_create_invoice_v2 (one atomic txn: invoice + line items +
    INVOICE_CREATED ledger + audit). issued_by defaults to the actor in the RPC.
    """
    result = call_rpc(
        "tr_create_invoice_v2",
        {
            "p_chapter_id": chapter_id,
            "p_member_id": member_id,
            "p_kind": kind,
            "p_amount_cents": amount_cents,
            "p_description": description,
            "p_actor_id": actor_id,
            "p_due_at": due_at,
            "p_issued_by": issued_by,
            "p_line_items": line_items,
            "p_idempotency_key": idempotency_key,
            "p_source_event_id": source_event_id,
        },
        sb=sb,
    )
    invoice = result.data
    recompute_member_balance(sb, member_id)
    notify_invoice_issued(
        chapter_id=chapter_id, member_id=member_id, invoice_id=invoice["id"], sb=sb
    )
    return invoice


def void_invoice(
    sb,
    *,
    chapter_id: str,
    invoice_id: str,
    actor_id: str,
    reason: str,
    idempotency_key: str | None = None,
) -> dict:
    """Void/waive an invoice (decision #5: Treasurer only, reason REQUIRED, logged).

    The RPC enforces the reason too; this guard gives callers a clear error
    before any DB round-trip.
    """
    if reason is None or not str(reason).strip():
        raise ValueError("a reason is required to void an invoice")
    result = call_rpc(
        "tr_void_invoice",
        {
            "p_chapter_id": chapter_id,
            "p_invoice_id": invoice_id,
            "p_actor_id": actor_id,
            "p_reason": reason,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    invoice = result.data
    recompute_member_balance(sb, invoice["member_id"])
    return invoice


# ── V1 presentation: open/void mapping + overdue flag ─────────────────────────
_V1_STATUS = {
    "unpaid": "open",
    "partially_paid": "open",
    "paid": "paid",
    "cancelled": "void",
}


def _parse_ts(value):
    from datetime import datetime, timezone

    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def present_invoice_v1(row: dict, *, now=None) -> dict:
    """Map a raw unpaid_invoices row to the V1 API shape.

    unpaid/partially_paid → "open", cancelled → "void"; raw status kept as
    `raw_status`; `overdue` = due_at < now while still open (decision #3).
    """
    from datetime import datetime, timezone

    now = now or datetime.now(timezone.utc)
    raw_status = row.get("status")
    due_at = _parse_ts(row.get("due_at"))
    overdue = bool(
        due_at is not None
        and raw_status in ("unpaid", "partially_paid")
        and due_at < now
    )
    out = dict(row)
    out["raw_status"] = raw_status
    out["status"] = _V1_STATUS.get(raw_status, raw_status)
    out["due_at"] = due_at.isoformat() if due_at is not None else None
    out["issued_by"] = row.get("issued_by")
    out["overdue"] = overdue
    return out


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
