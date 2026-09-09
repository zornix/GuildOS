"""Append-only Big Ledger writer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from api.platform.rows import unwrap_row
from api.treasury.core.clock import Clock, SystemClock


class EntryType(str, Enum):
    INVOICE_CREATED = "INVOICE_CREATED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    EXPENSE_APPROVED = "EXPENSE_APPROVED"
    EXPENSE_REVERSED = "EXPENSE_REVERSED"
    ADJUSTMENT_CREATED = "ADJUSTMENT_CREATED"
    REFUND_ISSUED = "REFUND_ISSUED"
    CANCEL_INVOICE = "CANCEL_INVOICE"


@dataclass(frozen=True)
class LedgerEntry:
    id: str
    chapter_id: str
    entry_type: str
    amount_cents: int
    member_id: str | None
    source_table: str
    source_id: str
    status: str
    created_at: Any
    reverses_entry_id: str | None = None


class LedgerWriter:
    def __init__(self, sb, clock: Clock | None = None):
        self._sb = sb
        self._clock = clock or SystemClock()

    def append(
        self,
        entry_type: EntryType,
        amount_cents: int,
        *,
        member_id: str | None,
        source_table: str,
        source_id: str,
        chapter_id: str,
        reverses: str | None = None,
    ) -> LedgerEntry:
        row = {
            "chapter_id": chapter_id,
            "created_at": self._clock.now().isoformat(),
            "entry_type": entry_type.value,
            "amount_cents": amount_cents,
            "member_id": member_id,
            "source_table": source_table,
            "source_id": source_id,
            "status": "active",
            "reverses_entry_id": reverses,
        }
        result = self._sb.table("big_ledger").insert(row).execute()
        data = unwrap_row(result)
        return LedgerEntry(
            id=str(data["id"]),
            chapter_id=str(data["chapter_id"]),
            entry_type=data["entry_type"],
            amount_cents=int(data["amount_cents"]),
            member_id=str(data["member_id"]) if data.get("member_id") else None,
            source_table=data["source_table"],
            source_id=str(data["source_id"]),
            status=data["status"],
            created_at=data["created_at"],
            reverses_entry_id=str(data["reverses_entry_id"]) if data.get("reverses_entry_id") else None,
        )

    def invalidate(self, entry_id: str, *, reason: str, actor_id: str) -> None:
        self._sb.table("big_ledger").update(
            {
                "status": "invalidated",
                "invalidated_reason": reason,
                "invalidated_by": actor_id,
                "invalidated_at": self._clock.now().isoformat(),
            }
        ).eq("id", entry_id).execute()
