import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from api.config import settings

router = APIRouter()
_CODE = re.compile(r"[A-Za-z0-9]{4,8}")


@router.get("/{short_code}")
def checkin_page(short_code: str):
    """Door-code links open the app for signed-in check-in."""
    if not _CODE.fullmatch(short_code):
        raise HTTPException(404, "Not found")
    return RedirectResponse(f"{settings.FRONTEND_URL.rstrip('/')}/?checkin={short_code}", status_code=302)
