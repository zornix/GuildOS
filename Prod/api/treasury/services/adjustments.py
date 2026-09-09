"""Adjustment service — manual balance corrections with a paper trail.

Delegates the atomic write to the tr_create_adjustment RPC, then refreshes the
affected balance scope (a member when member-scoped; the cache is the only thing
the BalanceEngine writes).
"""

from __future__ import annotations

from api.treasury.core.balance import BalanceEngine
from api.platform.rpc import call_rpc

# Adjustments at or above this magnitude (cents) need a second officer's sign-off
# before they take effect. Cheap insurance against one mistaken/compromised officer
# moving large sums. Tunable; 0 disables the gate.
LARGE_ADJUSTMENT_THRESHOLD_CENTS = 50_000


def create_adjustment(
    sb,
    *,
    chapter_id: str,
    member_id: str | None,
    kind: str,
    delta_cents: int,
    reason: str,
    officer_id: str,
    idempotency_key: str | None = None,
    threshold_cents: int = LARGE_ADJUSTMENT_THRESHOLD_CENTS,
) -> dict:
    result = call_rpc(
        "tr_create_adjustment",
        {
            "p_chapter_id": chapter_id,
            "p_member_id": member_id,
            "p_kind": kind,
            "p_delta_cents": delta_cents,
            "p_reason": reason,
            "p_actor_id": officer_id,
            "p_idempotency_key": idempotency_key,
            "p_threshold_cents": threshold_cents,
        },
        sb=sb,
    )
    adj = result.data

    # Refresh the affected member's cached balance (chapter-level adjustments move
    # only the chapter balance, which is computed on read — no cache to refresh).
    # A 'pending' adjustment has no effect until a second officer activates it.
    if member_id is not None and adj.get("status") == "active":
        BalanceEngine(sb).recompute_member(member_id)

    return adj


def approve_adjustment(
    sb,
    *,
    chapter_id: str,
    adjustment_id: str,
    approver_id: str,
) -> dict:
    """Second-officer activation of a pending (over-threshold) adjustment."""
    result = call_rpc(
        "tr_approve_adjustment",
        {
            "p_chapter_id": chapter_id,
            "p_adjustment_id": adjustment_id,
            "p_approver_id": approver_id,
        },
        sb=sb,
    )
    adj = result.data
    if adj.get("member_id") is not None and adj.get("status") == "active":
        BalanceEngine(sb).recompute_member(adj["member_id"])
    return adj
