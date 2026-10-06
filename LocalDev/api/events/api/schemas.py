"""Events domain-local Pydantic schemas (never shared across domains)."""

from __future__ import annotations

from datetime import date, time
from typing import Optional

from pydantic import BaseModel, Field, field_validator

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


class CompletenessItem(BaseModel):
    key: str
    required: int
    current: int
    met: bool


class Completeness(BaseModel):
    is_complete: bool
    items: list[CompletenessItem]


class SupervisorAdd(BaseModel):
    member_id: str


class OrganizerAdd(BaseModel):
    member_id: Optional[str] = None  # omitted = self-volunteer


class CheckInLinkResponse(BaseModel):
    short_code: str
    url: str
    expires_at: str


class NotifyConfirm(BaseModel):
    """Two-phase confirm: the recipient count the sender saw on the preview."""

    confirmed_recipient_count: int = Field(ge=0)


class NotifyPreviewOut(BaseModel):
    event_id: str
    completeness: Completeness
    recipient_count: int
    no_phone_count: int
    no_consent_count: int
    body_preview: str
    last_notified_at: Optional[str] = None


# ── Security assignments + swaps ─────────────────────────

class SecurityAssignIn(BaseModel):
    member_id: str


class SwapRequestIn(BaseModel):
    target_member_id: str
    note: Optional[str] = None


class SwapOut(BaseModel):
    id: str
    task_id: str
    event_id: str
    requester_member_id: str
    target_member_id: str
    note: Optional[str] = None
    status: str
    created_at: Optional[str] = None


class SecurityAssignmentOut(BaseModel):
    task_id: str
    event_id: str
    member_id: Optional[str] = None   # active-commitment holder (NULL if removed)
    status: str
    rejection_reason: Optional[str] = None
    pending_swap: Optional[SwapOut] = None
