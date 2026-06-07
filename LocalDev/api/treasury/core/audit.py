"""Append-only Treasury audit logger."""

from __future__ import annotations

from enum import Enum

from api.treasury.core.clock import Clock, SystemClock


class AuditAction(str, Enum):
    CREATE_INVOICE = "CREATE_INVOICE"
    VERIFY_PAYMENT = "VERIFY_PAYMENT"
    REJECT_PAYMENT = "REJECT_PAYMENT"
    CREATE_EXPENSE = "CREATE_EXPENSE"
    INVALIDATE_EXPENSE = "INVALIDATE_EXPENSE"
    CREATE_ADJUSTMENT = "CREATE_ADJUSTMENT"
    CANCEL_INVOICE = "CANCEL_INVOICE"
    ISSUE_REFUND = "ISSUE_REFUND"
    REBUILD = "REBUILD"


class AuditLogger:
    def __init__(self, sb, clock: Clock | None = None):
        self._sb = sb
        self._clock = clock or SystemClock()

    def record(
        self,
        action: AuditAction,
        *,
        actor_id: str,
        target_table: str,
        target_id: str,
        chapter_id: str,
        metadata: dict,
    ) -> None:
        self._sb.table("audit_logs").insert(
            {
                "chapter_id": chapter_id,
                "created_at": self._clock.now().isoformat(),
                "action": action.value,
                "actor_id": actor_id,
                "target_table": target_table,
                "target_id": target_id,
                "metadata": metadata,
            }
        ).execute()
