"""Attendance API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SessionCreate(BaseModel):
    event_id: str
    mode: str = Field(default="short_link", pattern="^(qr|short_link|manual)$")
    closes_at: datetime | None = None


class ExcuseCreate(BaseModel):
    reason: str


class ExcuseReview(BaseModel):
    status: str  # "approved" or "denied"


class ManualAttendance(BaseModel):
    status: str  # "present", "excused", or "absent"
    reason: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("present", "excused", "absent"):
            raise ValueError("Status must be 'present', 'excused', or 'absent'")
        return v
