import re

from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import date, time


class InviteRequest(BaseModel):
    emails: list[EmailStr]


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    role: str
    chapter_id: str
    chapter_name: Optional[str] = None


class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    date: date
    time: time
    location: str
    required: bool = False
    fine_amount: float = 0.0


class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    date: Optional[date] = None
    time: Optional[time] = None
    location: Optional[str] = None
    required: Optional[bool] = None
    fine_amount: Optional[float] = None


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


class ExcuseCreate(BaseModel):
    reason: str


class ExcuseReview(BaseModel):
    status: str  # "approved" or "denied"


class FineSummary(BaseModel):
    total_unpaid: float
    total_paid: float
    total_waived: float
    count_unpaid: int


class PhoneCheckIn(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) != 10:
            raise ValueError("Phone number must be 10 digits")
        return digits


