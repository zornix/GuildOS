"""Recruitment HTTP surface. Mounted under `/api/recruitment` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.recruitment.api.schemas import RecruitCreate, RecruitStageUpdate
from api.recruitment.auth import PIPELINE_UPDATE, PIPELINE_VIEW
from api.rbac.auth import require_permission
from api.platform.db import get_db
from api.platform.errors import public_message
from api.recruitment.services import pipeline as svc

router = APIRouter()

# rc_update_recruit_stage's RAISE EXCEPTION texts (not-found is its own class).
_KNOWN_RPC_ERRORS = {
    r"invalid recruit stage": "That is not a valid recruitment stage",
    r"actor \S+ is not an active member of chapter": "You are not an active member of this chapter",
}


def _http_error(exc: svc.RecruitmentError) -> HTTPException:
    """Map recruitment domain errors onto HTTP statuses (mirrors the at_* routes)."""
    if isinstance(exc, svc.RecruitNotFound):
        return HTTPException(404, "Recruit not found")
    if isinstance(exc, svc.InvalidPhone):
        return HTTPException(422, str(exc))  # our own validation text
    message = public_message(exc, _KNOWN_RPC_ERRORS, "That change could not be saved")
    if isinstance(exc, svc.NotPermitted):
        return HTTPException(403, message)
    if isinstance(exc, svc.InvalidStage):
        return HTTPException(422, message)
    return HTTPException(400, message)


@router.get("/recruits")
async def list_recruits(
    stage: str | None = None,
    user=Depends(require_permission(PIPELINE_VIEW)),
):
    return svc.list_recruits(get_db(), chapter_id=user["chapter_id"], stage=stage)


@router.post("/recruits")
async def create_recruit(
    body: RecruitCreate,
    user=Depends(require_permission(PIPELINE_UPDATE)),
):
    try:
        return svc.create_recruit(
            get_db(),
            chapter_id=user["chapter_id"],
            name=body.name,
            email=body.email,
            phone=body.phone,
            notes=body.notes,
            actor_id=user["id"],
        )
    except svc.RecruitmentError as exc:
        raise _http_error(exc) from exc


@router.post("/recruits/{recruit_id}/stage")
async def update_recruit_stage(
    recruit_id: str,
    body: RecruitStageUpdate,
    user=Depends(require_permission(PIPELINE_UPDATE)),
):
    try:
        return svc.update_stage(
            get_db(),
            chapter_id=user["chapter_id"],
            recruit_id=recruit_id,
            stage=body.stage,
            actor_id=user["id"],
        )
    except svc.RecruitmentError as exc:
        raise _http_error(exc) from exc
