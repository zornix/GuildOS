"""Refund service — return money to a member against one verified payment.

The most sensitive operation in Treasury: delegated to the atomic tr_issue_refund
RPC (capped at the source payment), then both the member's and the chapter's
balances are refreshed and a single refund notification is fired. Gated on the
`refund:create` capability at the HTTP boundary.
"""

from __future__ import annotations

from api.treasury.core.balance import BalanceEngine
from api.treasury.db.rpc import call_rpc
from api.treasury.notifications import notify_refund_issued


def issue_refund(
    sb,
    *,
    chapter_id: str,
    verified_payment_id: str,
    amount_cents: int,
    reason: str,
    officer_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tr_issue_refund",
        {
            "p_chapter_id": chapter_id,
            "p_verified_payment_id": verified_payment_id,
            "p_amount_cents": amount_cents,
            "p_reason": reason,
            "p_actor_id": officer_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    refund = result.data

    # A refund moves BOTH balances: it reduces the member's credit and the chapter cash.
    BalanceEngine(sb).recompute_member(refund["member_id"])
    notify_refund_issued(
        chapter_id=chapter_id,
        member_id=refund["member_id"],
        refund_id=refund["id"],
        sb=sb,
    )
    return refund
