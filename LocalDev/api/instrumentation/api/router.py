from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.instrumentation.api.usage import router as _usage_router  # noqa: E402

router.include_router(_usage_router)
