from fastapi import APIRouter, Depends

from api.dependencies import get_current_user, require_officer
from api.services.operations import (
    apply_template_to_event,
    get_event_readiness,
    list_event_templates,
)

router = APIRouter()


@router.get("/templates")
async def get_templates(user=Depends(get_current_user)):
    return list_event_templates(user["chapter_id"])


@router.post("/events/{event_id}/apply-template/{template_id}")
async def apply_template(event_id: str, template_id: str, officer=Depends(require_officer)):
    return apply_template_to_event(
        event_id=event_id,
        template_id=template_id,
        chapter_id=officer["chapter_id"],
    )


@router.get("/events/{event_id}/readiness")
async def event_readiness(event_id: str, user=Depends(get_current_user)):
    return get_event_readiness(event_id=event_id, chapter_id=user["chapter_id"])
