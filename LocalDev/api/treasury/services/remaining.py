"""Cents still owed per invoice. The one place this is computed in Python."""
from __future__ import annotations


def remaining_by_invoice(sb, invoices: list[dict]) -> dict[str, int]:
    if not invoices:
        return {}
    rows = (
        sb.table("payment_allocations")
        .select("invoice_id, amount_cents, reverses_allocation_id")
        .in_("invoice_id", [inv["id"] for inv in invoices])
        .execute()
    ).data or []
    allocated: dict[str, int] = {}
    for row in rows:
        sign = 1 if row["reverses_allocation_id"] is None else -1
        allocated[row["invoice_id"]] = allocated.get(row["invoice_id"], 0) + sign * int(row["amount_cents"])
    return {
        inv["id"]: max(int(inv["amount_cents"]) - allocated.get(inv["id"], 0), 0)
        for inv in invoices
    }
