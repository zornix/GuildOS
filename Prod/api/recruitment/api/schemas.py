"""Recruitment API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecruitCreate(BaseModel):
    name: str = Field(min_length=1)
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


class RecruitStageUpdate(BaseModel):
    stage: str = Field(
        pattern="^(lead|contacted|attended_event|bid_extended|bid_accepted|dropped)$"
    )
