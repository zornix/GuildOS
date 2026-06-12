from fastapi import APIRouter
from .cron import router as _cron_router

router = APIRouter()
router.include_router(_cron_router)
