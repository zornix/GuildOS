"""Recruitment HTTP surface. Mounted under `/api/recruitment` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.recruitment.api.schemas import RecruitCreate, RecruitStageUpdate
from api.recruitment.auth import PIPELINE_UPDATE, PIPELINE_VIEW, require_permission
from api.recruitment.services import pipeline as svc
from api.recruitment.services.pipeline import get_recruitment_db

router = APIRouter()


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
    return svc.create_recruit(
        get_recruitment_db(),
        chapter_id=user["chapter_id"],
        name=body.name,
        email=body.email,
        phone=body.phone,
        notes=body.notes,
        actor_id=user["id"],
    )


@router.post("/recruits/{recruit_id}/stage")
async def update_recruit_stage(
    recruit_id: str,
    body: RecruitStageUpdate,
    user=Depends(require_permission(PIPELINE_UPDATE)),
):
    updated = svc.update_stage(
        get_recruitment_db(),
        chapter_id=user["chapter_id"],
        recruit_id=recruit_id,
        stage=body.stage,
    )
    if not updated:
        raise HTTPException(404, "Recruit not found")
    return updated
