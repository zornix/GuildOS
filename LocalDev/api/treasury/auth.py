"""Capability-based Treasury authorization."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException

from api.db import get_supabase_admin
from api.dependencies import get_current_user

TREASURY_READ = "treasury:read"
INVOICE_CREATE = "invoice:create"
PAYMENT_REVIEW = "payment:review"
EXPENSE_CREATE = "expense:create"
ADJUSTMENT_CREATE = "adjustment:create"
REFUND_CREATE = "refund:create"
REBUILD_RUN = "rebuild:run"

CAPABILITIES = {
    TREASURY_READ,
    INVOICE_CREATE,
    PAYMENT_REVIEW,
    EXPENSE_CREATE,
    ADJUSTMENT_CREATE,
    REFUND_CREATE,
    REBUILD_RUN,
}


def require_capability(capability: str) -> Callable:
    if capability not in CAPABILITIES:
        raise ValueError(f"Unknown Treasury capability: {capability}")

    async def dependency(user=Depends(get_current_user)):
        sb = get_supabase_admin()
        result = (
            sb.table("treasury_grants")
            .select("id")
            .eq("chapter_id", user["chapter_id"])
            .eq("member_id", user["id"])
            .eq("capability", capability)
            .maybe_single()
            .execute()
        )
        if not result.data:
            raise HTTPException(403, f"Missing Treasury capability: {capability}")
        return user

    return dependency
