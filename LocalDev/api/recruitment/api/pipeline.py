"""Recruitment HTTP surface. Mounted under `/api/recruitment` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.recruitment.api.schemas import RecruitCreate, RecruitStageUpdate
from api.recruitment.auth import PIPELINE_UPDATE, PIPELINE_VIEW, require_permission
from api.recruitment.db.session import get_recruitment_db
from api.recruitment.services import pipeline as svc

router = APIRouter()


def _http_error(exc: svc.RecruitmentError) -> HTTPException:
    """Map recruitment domain errors onto HTTP statuses (mirrors the at_* routes)."""
    if isinstance(exc, svc.RecruitNotFound):
        return HTTPException(404, "Recruit not found")
    if isinstance(exc, svc.NotPermitted):
        return HTTPException(403, str(exc))
    if isinstance(exc, (svc.InvalidStage, svc.InvalidPhone)):
        return HTTPException(422, str(exc))
    return HTTPException(400, str(exc))


@router.get("/recruits")
async def list_recruits(
    stage: str | None = None,
    user=Depends(require_permission(PIPELINE_VIEW)),
):
    return svc.list_recruits(get_recruitment_db(), chapter_id=user["chapter_id"], stage=stage)


@router.post("/recruits")
async def create_recruit(
    body: RecruitCreate,
    user=Depends(require_permission(PIPELINE_UPDATE)),
):
    try:
        return svc.create_recruit(
            get_recruitment_db(),
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
            get_recruitment_db(),
            chapter_id=user["chapter_id"],
            recruit_id=recruit_id,
            stage=body.stage,
            actor_id=user["id"],
        )
    except svc.RecruitmentError as exc:
        raise _http_error(exc) from exc
