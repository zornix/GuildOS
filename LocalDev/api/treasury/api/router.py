"""Top-level Treasury router.

Downstream chunks include their sub-routers here. `api/index.py` mounts this
router once at `/api/treasury`.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

# Each chunk appends its sub-router include here (append-only; never remove another).
from api.treasury.api.invoices import router as _invoices_router  # noqa: E402
from api.treasury.api.expenses import router as _expenses_router  # noqa: E402
from api.treasury.api.balances import router as _balances_router  # noqa: E402
from api.treasury.api.reports import router as _reports_router  # noqa: E402  Chunk F
from api.treasury.api.payments import router as _payments_router  # noqa: E402  Chunk C
from api.treasury.api.adjustments import router as _adjustments_router  # noqa: E402  Chunk E
from api.treasury.api.refunds import router as _refunds_router  # noqa: E402  Chunk E
from api.treasury.api.rebuild import router as _rebuild_router  # noqa: E402  Chunk G

router.include_router(_invoices_router)
router.include_router(_expenses_router)
router.include_router(_balances_router)
router.include_router(_reports_router)
router.include_router(_payments_router)
router.include_router(_adjustments_router)
router.include_router(_refunds_router)
router.include_router(_rebuild_router)
