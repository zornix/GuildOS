from fastapi import APIRouter, Depends

from api.dependencies import require_officer
from api.services.checkin_links import list_active_links_for_chapter

router = APIRouter()


@router.get("/active")
async def active_checkin_links(officer=Depends(require_officer)):
    """List all active, non-expired check-in links for the officer's chapter."""
    return await list_active_links_for_chapter(officer["chapter_id"])
