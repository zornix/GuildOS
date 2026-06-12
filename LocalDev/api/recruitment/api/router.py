"""Top-level Recruitment router. Mounted at `/api/recruitment` by `api/index.py`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.recruitment.api.pipeline import router as _pipeline_router  # noqa: E402

router.include_router(_pipeline_router)
