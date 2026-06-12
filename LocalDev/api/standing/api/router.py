from fastapi import APIRouter
from .standing import router as _standing_router

router = APIRouter()
router.include_router(_standing_router)
