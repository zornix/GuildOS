"""Top-level RBAC router. Mounted at `/api/rbac` by `api/index.py`."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.rbac.api.roles import router as _roles_router  # noqa: E402

router.include_router(_roles_router)
