from fastapi import APIRouter, Depends

from api.attendance.auth import CHECKIN_LINK_MANAGE
from api.rbac.auth import require_permission
from api.attendance.services.checkin_links import list_active_links_for_chapter

router = APIRouter()


@router.get("/active")
async def active_checkin_links(
    officer=Depends(require_permission(CHECKIN_LINK_MANAGE)),
):
    """List all active, non-expired check-in links for the caller's chapter."""
    return await list_active_links_for_chapter(officer["chapter_id"])
