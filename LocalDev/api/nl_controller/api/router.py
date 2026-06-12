"""Top-level NL controller router. Mounted at `/api/nl-controller` by `api/index.py`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.nl_controller.api.commands import router as _commands_router  # noqa: E402

router.include_router(_commands_router)
