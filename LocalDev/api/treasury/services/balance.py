"""Member balance service — read API + cache refresh over BalanceEngine."""

from __future__ import annotations

from api.treasury.core.balance import BalanceEngine


def get_member_balance(sb, *, member_id: str) -> dict:
    """Return the cached balance, refreshing it first so cache == freshly computed."""
    engine = BalanceEngine(sb)
    engine.recompute_member(member_id)
    row = (
        sb.table("member_finance_accounts")
        .select("*")
        .eq("member_id", member_id)
        .maybe_single()
        .execute()
    ).data
    if not row:
        return {
            "member_id": member_id,
            "total_owed_cents": 0,
            "total_paid_cents": 0,
            "outstanding_balance_cents": 0,
            "current_balance_cents": 0,
        }
    return {
        "member_id": member_id,
        "total_owed_cents": int(row["total_owed_cents"]),
        "total_paid_cents": int(row["total_paid_cents"]),
        "outstanding_balance_cents": int(row["outstanding_balance_cents"]),
        "current_balance_cents": int(row["current_balance_cents"]),
    }
