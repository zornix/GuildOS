"""Top-level MemberAdmin router.

Mounted at `/api/memberadmin` by `api/index.py`. Standing is exposed separately at
`/api/standing` for backward compatibility with the active frontend.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

from api.memberadmin.api.scores import router as _scores_router  # noqa: E402

router.include_router(_scores_router)
