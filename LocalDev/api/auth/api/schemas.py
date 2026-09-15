from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional

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
    # Set only when the officer confirms these people signed an SMS opt-in (#57).
    # Applies to every address in the batch; default false.
    sms_consent: bool = False


class RedeemSetupCodeRequest(BaseModel):
    email: EmailStr
    code: str


