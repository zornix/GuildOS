"""Top-level Events router. Mounted at `/api/events` by `api/index.py`.

Aggregates the domain's route handlers (api/events/api/events.py). Legacy
paths and response shapes are preserved; the V1 build only ADDS routes/fields.
"""

from __future__ import annotations

from fastapi import APIRouter

from .events import router as _events_router
from .notifications import router as _notifications_router

router = APIRouter()
router.include_router(_events_router)
router.include_router(_notifications_router)
