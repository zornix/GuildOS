"""Attendance API schemas (domain-local, Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from api.phone import to_e164


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


class PhoneCheckIn(BaseModel):
    """A phone check-in body. `phone` is normalized to E.164 on the way in.

    The check-in page posts 10 bare digits; members are stored in E.164
    (migration 0149). Normalizing here — through the one sanctioned converter —
    means the lookup in the route compares like with like, whatever the member
    typed. The previous validator demanded exactly 9 digits, which no client
    ever sent and no member row ever held, so every phone check-in 422'd.
    """

    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        normalized = to_e164(v)
        if normalized is None:
            raise ValueError("Enter a valid US phone number")
        return normalized

