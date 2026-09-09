"""Member treasury dashboard read (V1, decision #3).

One aggregate read: computed balance (BalanceEngine), pending submissions
("pending balance"), open invoices with remaining/overdue, recent activity.
Overdue invoices remain visible here until covered or voided.
"""

from __future__ import annotations

from datetime import datetime, timezone

from api.treasury.core.balance import BalanceEngine


def _parse_ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _net_allocated_cents(sb, invoice_id: str) -> int:
    rows = (
        sb.table("payment_allocations")
        .select("amount_cents, reverses_allocation_id")
        .eq("invoice_id", invoice_id)
        .execute()
    ).data or []
    return sum(
        int(r["amount_cents"]) if r["reverses_allocation_id"] is None else -int(r["amount_cents"])
        for r in rows
    )


def _direct_paid_cents(sb, invoice_id: str) -> int:
    rows = (
        sb.table("verified_payments")
        .select("amount_cents")
        .eq("invoice_id", invoice_id)
        .execute()
    ).data or []
    return sum(int(r["amount_cents"]) for r in rows)


def get_member_dashboard(sb, *, chapter_id: str, member_id: str, now=None) -> dict:
    now = now or datetime.now(timezone.utc)

    # Balance — computed via the existing BalanceEngine (refreshes the cache too).
    engine = BalanceEngine(sb)
    engine.recompute_member(member_id)
    balance = (
        sb.table("member_finance_accounts")
        .select("*")
        .eq("member_id", member_id)
        .maybe_single()
        .execute()
    ).data or {
        "total_owed_cents": 0,
        "total_paid_cents": 0,
        "current_balance_cents": 0,
        "outstanding_balance_cents": 0,
    }

    # Pending submissions — visible to the member as "pending balance".
    pending = (
        sb.table("payment_submissions")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .eq("status", "pending")
        .order("created_at")
        .execute()
    ).data or []
    pending_submissions = [{**row, "state": "pending balance"} for row in pending]
    pending_cents = sum(int(r["claimed_amount_cents"]) for r in pending)

    # Open invoices (unpaid + partially paid) with remaining / overdue / source.
    invoices = (
        sb.table("unpaid_invoices")
        .select("*")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .in_("status", ["unpaid", "partially_paid"])
        .order("created_at")
        .execute()
    ).data or []
    open_invoices = []
    for inv in invoices:
        remaining = (
            int(inv["amount_cents"])
            - _direct_paid_cents(sb, inv["id"])
            - _net_allocated_cents(sb, inv["id"])
        )
        due_at = _parse_ts(inv.get("due_at"))
        open_invoices.append(
            {
                "id": inv["id"],
                "description": inv.get("description"),
                "amount_cents": int(inv["amount_cents"]),
                "remaining_cents": max(0, remaining),
                "due_at": due_at.isoformat() if due_at else None,
                "overdue": bool(due_at is not None and due_at < now),
                "source": inv.get("kind"),
                "status": "open",
                "raw_status": inv.get("status"),
            }
        )

    # Recent activity — last ledger entries for the member (newest first).
    activity = (
        sb.table("big_ledger")
        .select("entry_type, amount_cents, source_table, source_id, created_at")
        .eq("chapter_id", chapter_id)
        .eq("member_id", member_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    ).data or []

    return {
        "member_id": member_id,
        "balance": balance,
        "pending_cents": pending_cents,
        "pending_submissions": pending_submissions,
        "open_invoices": open_invoices,
        "recent_activity": activity,
    }
