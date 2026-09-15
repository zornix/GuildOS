from pydantic import BaseModel, EmailStr, field_validator

from api.phone import to_e164


class CreateChapterRequest(BaseModel):
    name: str
    organization: str | None = None
    school: str | None = None
    officer_name: str
    officer_email: EmailStr
    officer_phone: str

    @field_validator("name", "officer_name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("officer_phone")
    @classmethod
    def _e164(cls, v: str) -> str:
        # The one sanctioned normalizer (api/phone.py); members.phone has a
        # matching CHECK, so anything it rejects would fail at the insert anyway.
        normalized = to_e164(v)
        if not normalized:
            raise ValueError("must be a phone number in E.164 form, e.g. +15551234567")
        return normalized
