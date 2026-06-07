"""Finance-adjustment HTTP surface.

Creating an adjustment requires the `adjustment:create` capability; activating a
large (over-threshold) adjustment requires a SECOND `adjustment:create` holder.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from api.treasury.auth import ADJUSTMENT_CREATE, require_capability
from api.treasury.db.session import get_treasury_db
from api.treasury.services import adjustments as svc

router = APIRouter()


class AdjustmentCreate(BaseModel):
    member_id: str | None = None  # null = chapter-level
    kind: str = Field(pattern="^(waive_fine|rent_correction|dues_forgiveness|manual_correction)$")
    delta_cents: int  # signed; no positivity constraint
    reason: str = Field(min_length=1)


@router.post("/adjustments")
async def create_adjustment(
    body: AdjustmentCreate,
    user=Depends(require_capability(ADJUSTMENT_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_treasury_db()
    return svc.create_adjustment(
        sb,
        chapter_id=user["chapter_id"],
        member_id=body.member_id,
        kind=body.kind,
        delta_cents=body.delta_cents,
        reason=body.reason,
        officer_id=user["id"],
        idempotency_key=idempotency_key,
    )


@router.post("/adjustments/{adjustment_id}/approve")
async def approve_adjustment(
    adjustment_id: str,
    user=Depends(require_capability(ADJUSTMENT_CREATE)),
):
    sb = get_treasury_db()
    return svc.approve_adjustment(
        sb,
        chapter_id=user["chapter_id"],
        adjustment_id=adjustment_id,
        approver_id=user["id"],
    )
