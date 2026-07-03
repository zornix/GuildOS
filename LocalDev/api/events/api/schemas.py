"""Events domain-local Pydantic schemas (never shared across domains)."""

from __future__ import annotations

from datetime import date, time
from typing import Optional

from pydantic import BaseModel, field_validator

from api.events.core.rules import AUDIENCE_TO_VISIBILITY, VISIBILITY_VALUES

_VISIBILITY_ERR = "visibility must be one of: " + ", ".join(VISIBILITY_VALUES)
_AUDIENCE_ERR = "audience must be one of: " + ", ".join(AUDIENCE_TO_VISIBILITY)


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    date: date
    time: time
    end_date: Optional[date] = None           # defaults to `date` when only end_time given
    end_time: Optional[time] = None
    invite_link: Optional[str] = None
    location: str
    required: bool = False
    finable: bool = False
    fine_amount: float = 0.0
    event_type: Optional[str] = None          # legacy free-text, kept as-is
    event_type_name: Optional[str] = None     # case-insensitive get-or-create
    visibility: str = "chapter"
    audience: Optional[str] = None            # all | officers | custom
    audience_member_ids: Optional[list[str]] = None
    event_group_id: Optional[str] = None
    group_with_event_id: Optional[str] = None

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        if v not in VISIBILITY_VALUES:
            raise ValueError(_VISIBILITY_ERR)
        return v

    @field_validator("audience")
    @classmethod
    def validate_audience(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in AUDIENCE_TO_VISIBILITY:
            raise ValueError(_AUDIENCE_ERR)
        return v


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    date: Optional[date] = None
    time: Optional[time] = None
    end_date: Optional[date] = None
    end_time: Optional[time] = None
    invite_link: Optional[str] = None
    location: Optional[str] = None
    required: Optional[bool] = None
    finable: Optional[bool] = None
    fine_amount: Optional[float] = None
    event_type: Optional[str] = None
    event_type_name: Optional[str] = None
    visibility: Optional[str] = None
    audience: Optional[str] = None
    audience_member_ids: Optional[list[str]] = None

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VISIBILITY_VALUES:
            raise ValueError(_VISIBILITY_ERR)
        return v

    @field_validator("audience")
    @classmethod
    def validate_audience(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in AUDIENCE_TO_VISIBILITY:
            raise ValueError(_AUDIENCE_ERR)
        return v


class SupervisorOut(BaseModel):
    member_id: str
    is_creator: bool = False
    name: Optional[str] = None


class EventResponse(BaseModel):
    id: str
    title: str
    date: str
    time: str
    end_date: Optional[str] = None
    end_time: Optional[str] = None
    invite_link: Optional[str] = None
    location: str
    required: bool
    finable: bool = False
    fine_amount: float
    checkin_active: bool = False
    attendance_count: Optional[int] = None
    organizer_count: int = 0
    organizers_needed: int = 0
    group_id: Optional[str] = None
    supervisor_member_id: Optional[str] = None  # deprecated (see CONFORM_TODO.md)
    supervisors: list[SupervisorOut] = []


class SupervisorSet(BaseModel):
    member_id: str


class SupervisorAdd(BaseModel):
    member_id: str


class OrganizerAdd(BaseModel):
    member_id: Optional[str] = None  # omitted = self-volunteer


class CheckInLinkResponse(BaseModel):
    short_code: str
    url: str
    expires_at: str
