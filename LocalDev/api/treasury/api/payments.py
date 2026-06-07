"""Payment review HTTP surface: verify, reject, fetch receipt.

Mounted on the Treasury router under `/api/treasury`. Verification and rejection
require the `payment:review` capability; reading a receipt requires `treasury:read`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from api.treasury.auth import PAYMENT_REVIEW, TREASURY_READ, require_capability
from api.treasury.db.session import get_treasury_db
from api.treasury.services import payments as svc

router = APIRouter()


class RejectBody(BaseModel):
    reason: str | None = None


@router.post("/payments/submissions/{submission_id}/verify")
async def verify_payment(
    submission_id: str,
    user=Depends(require_capability(PAYMENT_REVIEW)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.verify_payment(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/payments/submissions/{submission_id}/reject")
async def reject_payment(
    submission_id: str,
    body: RejectBody | None = None,
    user=Depends(require_capability(PAYMENT_REVIEW)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.reject_payment(
        sb,
        chapter_id=user["chapter_id"],
        submission_id=submission_id,
        actor_id=user["id"],
        reason=body.reason if body else None,
        idempotency_key=idempotency_key,
    )


@router.get("/payments/receipts/{receipt_id}")
async def get_receipt(
    receipt_id: str,
    user=Depends(require_capability(TREASURY_READ)),
):
    sb = get_treasury_db()
    receipt = svc.get_receipt(sb, chapter_id=user["chapter_id"], receipt_id=receipt_id)
    if receipt is None:
        raise HTTPException(404, "Receipt not found")
    return receipt
