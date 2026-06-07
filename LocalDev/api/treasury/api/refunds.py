"""Refund HTTP surface — return money to a member, gated on `refund:create`.

The most sensitive Treasury write: capped at the source verified payment and
idempotent on the `Idempotency-Key` header.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from api.treasury.auth import REFUND_CREATE, require_capability
from api.treasury.db.session import get_treasury_db
from api.treasury.services import refunds as svc

router = APIRouter()


class RefundCreate(BaseModel):
    verified_payment_id: str
    amount_cents: int = Field(gt=0)
    reason: str = Field(min_length=1)


@router.post("/refunds")
async def issue_refund(
    body: RefundCreate,
    user=Depends(require_capability(REFUND_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.issue_refund(
        sb,
        chapter_id=user["chapter_id"],
        verified_payment_id=body.verified_payment_id,
        amount_cents=body.amount_cents,
        reason=body.reason,
        officer_id=user["id"],
        idempotency_key=idempotency_key,
    )
