"""Top-level Events router. Mounted at `/api/events` by `api/index.py`.

Behavior-preserving conformance (§2.4): the handlers are the existing flat
module, included here unchanged so all paths and e2e specs stay green.
"""

from __future__ import annotations

from fastapi import APIRouter

from .events import router as _legacy_events_router

router = APIRouter()
router.include_router(_legacy_events_router)
