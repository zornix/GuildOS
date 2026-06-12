"""NL controller HTTP surface. Mounted under `/api/nl-controller` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.nl_controller.api.schemas import CommandReview, CommandSubmit
from api.nl_controller.auth import NL_APPROVE, NL_EXECUTE, require_permission
from api.nl_controller.services import commands as svc
from api.nl_controller.services.commands import get_nl_db

router = APIRouter()


@router.get("/commands")
async def list_commands(
    status: str | None = None,
    user=Depends(require_permission(NL_EXECUTE, NL_APPROVE)),
):
    return svc.list_commands(get_nl_db(), chapter_id=user["chapter_id"], status=status)


@router.post("/commands")
async def submit_command(
    body: CommandSubmit,
    user=Depends(require_permission(NL_EXECUTE)),
):
    return svc.submit_command(
        get_nl_db(),
        chapter_id=user["chapter_id"],
        input_text=body.input_text,
        actor_id=user["id"],
    )


@router.post("/commands/{command_id}/review")
async def review_command(
    command_id: str,
    body: CommandReview,
    user=Depends(require_permission(NL_APPROVE)),
):
    reviewed = svc.review_command(
        get_nl_db(),
        chapter_id=user["chapter_id"],
        command_id=command_id,
        decision=body.decision,
        actor_id=user["id"],
    )
    if not reviewed:
        raise HTTPException(404, "Command not found or not pending approval")
    return reviewed
