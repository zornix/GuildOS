"""Top-level Initiatives router. Mounted at `/api/initiatives` by `api/index.py`.

Aggregates the domain's route handlers (api/initiatives/api/initiatives.py).
"""

from __future__ import annotations

from fastapi import APIRouter

from .initiatives import router as _initiatives_router

router = APIRouter()
router.include_router(_initiatives_router)
