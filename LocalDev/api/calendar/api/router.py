from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.calendar.api.calendar import router as _calendar_router  # noqa: E402

router.include_router(_calendar_router)
