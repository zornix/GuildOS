"""Top-level Bylaws router. Mounted at `/api/bylaws` by `api/index.py`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.bylaws.api.documents import router as _documents_router  # noqa: E402

router.include_router(_documents_router)
