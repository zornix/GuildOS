"""Attendance domain routers.

`router` is mounted at `/api/attendance` by `api/index.py` and combines the
legacy attendance handlers (unchanged) with the new sessions surface. The
excuses / checkin-links / checkin-page routers keep their own mount prefixes,
so they are re-exported here for index.py rather than nested.
"""

from __future__ import annotations

from fastapi import APIRouter

from .attendance import router as _legacy_attendance_router
from .checkin_links import router as checkin_links_router  # noqa: F401
from .checkin_page import router as checkin_page_router  # noqa: F401
from .excuses import router as excuses_router  # noqa: F401

from api.attendance.api.sessions import router as _sessions_router
from api.attendance.api.summary import router as _summary_router

router = APIRouter()
# /summary is a fixed path: include it before the legacy router so it is never
# shadowed by parameterized legacy routes.
router.include_router(_summary_router)
router.include_router(_legacy_attendance_router)
router.include_router(_sessions_router)
