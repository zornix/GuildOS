"""Rebuild HTTP surface — Chunk G.

POST /rebuild — reconstruct the ledger + balances from operational tables, diff
against the live ledger and balance cache, and return a drift report. Gated on the
`rebuild:run` capability. With `?apply_repairs=true` the balance cache (only) is
overwritten to match the reconstruction; `big_ledger` is never mutated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.treasury.auth import REBUILD_RUN, require_capability
from api.treasury.db.session import get_treasury_db
from api.treasury.services import rebuild as svc

router = APIRouter()


@router.post("/rebuild")
async def run_rebuild(
    apply_repairs: bool = Query(default=False),
    user=Depends(require_capability(REBUILD_RUN)),
):
    sb = get_treasury_db()
    return svc.run_rebuild(sb, chapter_id=user["chapter_id"], apply_repairs=apply_repairs)
