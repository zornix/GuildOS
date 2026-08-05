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


class RedeemSetupCodeRequest(BaseModel):
    email: EmailStr
    code: str


