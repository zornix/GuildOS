"""Top-level Tasks router. Mounted at `/api/tasks` by `api/index.py`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.tasks.api.commitments import router as _commitments_router  # noqa: E402
from api.tasks.api.tasks import router as _tasks_router  # noqa: E402

# Commitments first: its literal segments (uncommit-log, attribution) must win
# over the generic /{task_id}/... routes in tasks.py.
router.include_router(_commitments_router)
router.include_router(_tasks_router)

