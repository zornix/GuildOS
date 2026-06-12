from pydantic import BaseModel
from typing import Optional
from datetime import date, time
from pydantic import field_validator

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    date: date
    time: time
    location: str
    required: bool = False
    fine_amount: float = 0.0
    event_type: Optional[str] = None
    visibility: str = "chapter"

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: str) -> str:
        if v not in ("chapter", "officer", "role_specific", "private"):
            raise ValueError("visibility must be chapter, officer, role_specific, or private")
        return v


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    date: Optional[date] = None
    time: Optional[time] = None
    location: Optional[str] = None
    required: Optional[bool] = None
    fine_amount: Optional[float] = None
    event_type: Optional[str] = None
    visibility: Optional[str] = None

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("chapter", "officer", "role_specific", "private"):
            raise ValueError("visibility must be chapter, officer, role_specific, or private")
        return v


class EventResponse(BaseModel):
    id: str
    title: str
    date: str
    time: str
    location: str
    required: bool
    fine_amount: float
    checkin_active: bool = False
    attendance_count: Optional[int] = None


class CheckInLinkResponse(BaseModel):
    short_code: str
    url: str
    expires_at: str



