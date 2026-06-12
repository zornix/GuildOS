"""Top-level Announcements router. Mounted at `/api/announcements` by `api/index.py`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.announcements.api.announcements import router as _announcements_router  # noqa: E402

router.include_router(_announcements_router)
