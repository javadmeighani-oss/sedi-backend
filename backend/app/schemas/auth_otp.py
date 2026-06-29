# app/schemas/auth_otp.py – Stage 25 Phone OTP + V1.1A unified profile + Gate 1
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from backend.app.services.gate1_access import validate_iana_timezone

DISPLAY_NAME_MAX_LENGTH = 64
SEX_MAX_LENGTH = 32
ADDRESSING_PREFERENCE_MAX_LENGTH = 64
BIRTH_YEAR_MIN = 1900


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
    """Unified profile read (GET/PATCH /auth/me)."""

    user_id: int
    phone: Optional[str] = None
    name: Optional[str] = None
    preferred_language: Optional[str] = None
    account_type: str = "normal"
    birth_year: Optional[int] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    addressing_preference: Optional[str] = None
    timezone: Optional[str] = None
    height_cm: Optional[int] = None
    weight_kg: Optional[float] = None
    # Backward-compatible aliases for existing clients
    display_name: Optional[str] = None
    language: Optional[str] = None


class MeUpdateIn(BaseModel):
    """PATCH /auth/me – partial update; at least one field required."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    display_name: Optional[str] = None
    preferred_language: Optional[Literal["en", "fa", "ar"]] = None
    birth_year: Optional[int] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    addressing_preference: Optional[str] = None
    timezone: Optional[str] = None
    height_cm: Optional[int] = None
    weight_kg: Optional[float] = None

    def resolved_name(self) -> Optional[str]:
        """Prefer `name`; fall back to legacy `display_name`."""
        if self.name is not None:
            return self.name
        if self.display_name is not None:
            return self.display_name
        return None

    @field_validator("name", "display_name")
    @classmethod
    def validate_name_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("name must not be empty")
        if len(trimmed) > DISPLAY_NAME_MAX_LENGTH:
            raise ValueError(f"name must be at most {DISPLAY_NAME_MAX_LENGTH} characters")
        return trimmed

    @field_validator("sex")
    @classmethod
    def validate_sex(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if len(trimmed) > SEX_MAX_LENGTH:
            raise ValueError(f"sex must be at most {SEX_MAX_LENGTH} characters")
        return trimmed

    @field_validator("addressing_preference")
    @classmethod
    def validate_addressing_preference(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if len(trimmed) > ADDRESSING_PREFERENCE_MAX_LENGTH:
            raise ValueError(
                f"addressing_preference must be at most {ADDRESSING_PREFERENCE_MAX_LENGTH} characters"
            )
        return trimmed

    @field_validator("birth_year")
    @classmethod
    def validate_birth_year(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        current_year = datetime.utcnow().year
        if value < BIRTH_YEAR_MIN or value > current_year:
            raise ValueError(f"birth_year must be between {BIRTH_YEAR_MIN} and {current_year}")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: Optional[str]) -> Optional[str]:
        return validate_iana_timezone(value)

    @field_validator("height_cm")
    @classmethod
    def validate_height(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        if value < 50 or value > 300:
            raise ValueError("height_cm must be between 50 and 300")
        return value

    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        if value < 1 or value > 500:
            raise ValueError("weight_kg must be between 1 and 500")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "MeUpdateIn":
        if all(
            v is None
            for v in (
                self.name,
                self.display_name,
                self.preferred_language,
                self.birth_year,
                self.date_of_birth,
                self.sex,
                self.addressing_preference,
                self.timezone,
                self.height_cm,
                self.weight_kg,
            )
        ):
            raise ValueError("At least one profile field is required")
        return self
