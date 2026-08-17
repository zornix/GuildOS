from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.platform.db import get_db
from api.calendar.services import calendar as svc
from api.dependencies import get_current_user
import api.instrumentation.services.usage as usage_svc

router = APIRouter()

# get_db must be importable here to satisfy conftest.py
# from api.calendar.api.calendar import get_db

@router.get("/")
async def list_calendar(
    start: str | None = None,
    end: str | None = None,
    user=Depends(get_current_user),
):
    # Validation
    if start and end and start > end:
        raise HTTPException(422, "start must be <= end")
        
    res = svc.get_calendar(
        get_db(),
        chapter_id=user["chapter_id"],
        member_id=user["id"],
        start=start,
        end=end,
    )
    
    # Fire and forget tracking
    try:
        usage_svc.track(
            get_db(), 
            chapter_id=user["chapter_id"],
            member_id=user["id"],
            event_name="calendar:viewed",
        )
    except Exception:
        pass
    
    return res
