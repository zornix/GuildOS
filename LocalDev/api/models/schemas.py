import re

from pydantic import BaseModel, EmailStr, field_validator, model_validator
from typing import Optional
from datetime import date, time


class LoginRequest(BaseModel):
    email: EmailStr
    password: Optional[str] = None


class SetPasswordRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


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


class ExcuseCreate(BaseModel):
    reason: str


class ExcuseReview(BaseModel):
    status: str  # "approved" or "denied"


class FineSummary(BaseModel):
    total_unpaid: float
    total_paid: float
    total_waived: float
    count_unpaid: int


class FineToInvoice(BaseModel):
    """Float→cents boundary for fines entering Treasury (Chunk A, §7.8).

    `fine_amount` arrives as a NUMERIC-serialized float from the legacy events/fines
    surface. This is the ONLY sanctioned conversion point; downstream Treasury code
    works in integer cents exclusively. The validator routes through Money.from_numeric
    (Decimal(str(v)) * 100, ROUND_HALF_UP) so no float math ever touches a money value.
    """

    fine_amount: float
    fine_amount_cents: int = 0

    @model_validator(mode="after")
    def _derive_cents(self) -> "FineToInvoice":
        from api.treasury.core.money import Money

        # Stringify the legacy float so Decimal sees the decimal literal, not the
        # binary-float artifact — Money.from_numeric rejects raw float by design.
        object.__setattr__(self, "fine_amount_cents", Money.from_numeric(str(self.fine_amount)).cents)
        return self


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
    phone: str

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) != 9:
            raise ValueError("Phone number must be 9 digits")
        return digits


