# app/schemas/auth_otp.py – Stage 25 Phone OTP
from typing import Literal, Optional

from pydantic import BaseModel, field_validator, model_validator

DISPLAY_NAME_MAX_LENGTH = 64


class OtpRequestIn(BaseModel):
    phone: str


class OtpRequestOut(BaseModel):
    ok: bool
    next: str = "verify_otp"


class OtpVerifyIn(BaseModel):
    phone: str
    code: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    user_id: int
    phone: Optional[str] = None
    display_name: Optional[str] = None
    language: Optional[str] = None


class MeUpdateIn(BaseModel):
    """PATCH /auth/me – at least one of preferred_language or display_name required."""

    preferred_language: Optional[Literal["en", "fa", "ar"]] = None
    display_name: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("display_name must not be empty")
        if len(trimmed) > DISPLAY_NAME_MAX_LENGTH:
            raise ValueError(f"display_name must be at most {DISPLAY_NAME_MAX_LENGTH} characters")
        return trimmed

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "MeUpdateIn":
        if self.preferred_language is None and self.display_name is None:
            raise ValueError("At least one of preferred_language or display_name is required")
        return self
