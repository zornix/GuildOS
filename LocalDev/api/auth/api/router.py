from fastapi import APIRouter
from .auth import router as _auth_router

router = APIRouter()
router.include_router(_auth_router)
