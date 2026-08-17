"""Expense service — money out, chapter-only. Delegates writes to tr_* RPCs."""

from __future__ import annotations

from api.treasury.core.balance import BalanceEngine
from api.treasury.core.money import Money
from api.platform.rpc import call_rpc


def create_expense(
    sb,
    *,
    chapter_id: str,
    category: str,
    amount_cents: int,
    description: str | None,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tr_create_expense",
        {
            "p_chapter_id": chapter_id,
            "p_category": category,
            "p_amount_cents": amount_cents,
            "p_description": description,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def invalidate_expense(
    sb,
    *,
    chapter_id: str,
    expense_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
) -> dict:
    result = call_rpc(
        "tr_invalidate_expense",
        {
            "p_chapter_id": chapter_id,
            "p_expense_id": expense_id,
            "p_actor_id": actor_id,
            "p_idempotency_key": idempotency_key,
        },
        sb=sb,
    )
    return result.data


def chapter_balance(sb, *, chapter_id: str) -> Money:
    return BalanceEngine(sb).chapter_balance(chapter_id)
