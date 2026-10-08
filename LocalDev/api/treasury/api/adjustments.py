"""Finance-adjustment HTTP surface.

Creating an adjustment requires the `treasury:adjustment:create` permission; activating a
large (over-threshold) adjustment requires a SECOND `treasury:adjustment:create` holder.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.treasury.services import adjustments as svc

# Catalog permission keys gating this surface (ADR-0001; 0147).
ADJUSTMENT_CREATE = "treasury:adjustment:create"

router = APIRouter()


class AdjustmentCreate(BaseModel):
    member_id: str | None = None  # null = chapter-level
    kind: str = Field(pattern="^(waive_fine|rent_correction|dues_forgiveness|manual_correction)$")
    delta_cents: int  # signed; no positivity constraint
    reason: str = Field(min_length=1)


@router.post("/adjustments")
def create_adjustment(
    body: AdjustmentCreate,
    user=Depends(require_permission(ADJUSTMENT_CREATE)),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    sb = get_db()
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
def approve_adjustment(
    adjustment_id: str,
    user=Depends(require_permission(ADJUSTMENT_CREATE)),
):
    sb = get_db()
    return svc.approve_adjustment(
        sb,
        chapter_id=user["chapter_id"],
        adjustment_id=adjustment_id,
        approver_id=user["id"],
    )
