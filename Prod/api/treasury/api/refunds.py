"""Refund HTTP surface — return money to a member, gated on `treasury:refund:create`.

The most sensitive Treasury write: capped at the source verified payment and
idempotent on the `Idempotency-Key` header.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.treasury.services import refunds as svc

# Catalog permission keys gating this surface (ADR-0001; 0147).
REFUND_CREATE = "treasury:refund:create"

router = APIRouter()


class RefundCreate(BaseModel):
    verified_payment_id: str
    amount_cents: int = Field(gt=0)
    reason: str = Field(min_length=1)


@router.post("/refunds")
async def issue_refund(
    body: RefundCreate,
    user=Depends(require_permission(REFUND_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
    return svc.issue_refund(
        sb,
        chapter_id=user["chapter_id"],
        verified_payment_id=body.verified_payment_id,
        amount_cents=body.amount_cents,
        reason=body.reason,
        officer_id=user["id"],
        idempotency_key=idempotency_key,
    )
