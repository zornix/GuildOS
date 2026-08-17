"""Rebuild HTTP surface — Chunk G.

POST /rebuild — reconstruct the ledger + balances from operational tables, diff
against the live ledger and balance cache, and return a drift report. Gated on the
`treasury:rebuild:run` permission. With `?apply_repairs=true` the balance cache (only) is
overwritten to match the reconstruction; `big_ledger` is never mutated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.treasury.services import rebuild as svc

# Catalog permission keys gating this surface (ADR-0001; 0147).
REBUILD_RUN = "treasury:rebuild:run"

router = APIRouter()


@router.post("/rebuild")
async def run_rebuild(
    apply_repairs: bool = Query(default=False),
    user=Depends(require_permission(REBUILD_RUN)),
):
    sb = get_db()
    return svc.run_rebuild(sb, chapter_id=user["chapter_id"], apply_repairs=apply_repairs)
