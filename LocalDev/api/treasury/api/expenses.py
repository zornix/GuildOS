"""Expenses & chapter-balance HTTP surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from api.dependencies import get_current_user
from api.treasury.auth import EXPENSE_CREATE, TREASURY_READ, require_capability
from api.treasury.db.session import get_treasury_db
from api.treasury.services import expenses as svc

router = APIRouter()


class ExpenseCreate(BaseModel):
    category: str = Field(pattern="^(event|supplies|philanthropy|maintenance)$")
    amount_cents: int = Field(gt=0)
    description: str | None = None


@router.get("/balance")
async def get_chapter_balance(user=Depends(require_capability(TREASURY_READ))):
    sb = get_treasury_db()
    bal = svc.chapter_balance(sb, chapter_id=user["chapter_id"])
    return {"chapter_id": user["chapter_id"], "balance_cents": bal.cents, "balance_display": bal.to_dollars_str()}


@router.post("/expenses")
async def create_expense(
    body: ExpenseCreate,
    user=Depends(require_capability(EXPENSE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
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
async def invalidate_expense(
    expense_id: str,
    user=Depends(require_capability(EXPENSE_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.invalidate_expense(
        sb,
        chapter_id=user["chapter_id"],
        expense_id=expense_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )
