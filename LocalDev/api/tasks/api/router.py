"""Top-level Tasks router. Mounted at `/api/tasks` by `api/index.py`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.tasks.api.tasks import router as _tasks_router  # noqa: E402

router.include_router(_tasks_router)

