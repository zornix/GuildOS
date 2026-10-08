"""Expenses & chapter-balance HTTP surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.treasury.services import expenses as svc

# Catalog permission keys gating this surface (ADR-0001; 0147).
EXPENSE_CREATE = "treasury:expense:create"
BALANCE_VIEW = "treasury:budget:view"

router = APIRouter()


class ExpenseCreate(BaseModel):
    category: str = Field(pattern="^(event|supplies|philanthropy|maintenance)$")
    amount_cents: int = Field(gt=0)
    description: str | None = None


@router.get("/balance")
def get_chapter_balance(user=Depends(require_permission(BALANCE_VIEW))):
    sb = get_db()
    bal = svc.chapter_balance(sb, chapter_id=user["chapter_id"])
    return {"chapter_id": user["chapter_id"], "balance_cents": bal.cents, "balance_display": bal.to_dollars_str()}


@router.post("/expenses")
def create_expense(
    body: ExpenseCreate,
    user=Depends(require_permission(EXPENSE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    return svc.create_expense(
        sb,
        chapter_id=user["chapter_id"],
        category=body.category,
        amount_cents=body.amount_cents,
        description=body.description,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/expenses/{expense_id}/invalidate")
def invalidate_expense(
    expense_id: str,
    user=Depends(require_permission(EXPENSE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    return svc.invalidate_expense(
        sb,
        chapter_id=user["chapter_id"],
        expense_id=expense_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )
