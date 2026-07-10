# app/schemas/gate1.py — Gate 1 profile facts, caregivers, dependents
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

GATE1_PROFILE_FACT_TYPES = frozenset({
    "allergy",
    "occupation",
    "living_situation",
    "independence_level",
    "care_need",
    "social_context",
    # Ongoing / current chronic condition narrative (not full structured user_conditions row).
    "chronic_condition_note",
    # Past major medical history: surgery, hospitalization, prior events (not active condition list).
    "medical_history_note",
    "other_identity",
})

GATE1_FACT_SOURCES = frozenset({"manual", "conversation", "system", "caregiver"})


def _validate_fact_type(value: str) -> str:
    v = (value or "").strip()
    if v not in GATE1_PROFILE_FACT_TYPES:
        raise ValueError(f"fact_type must be one of: {', '.join(sorted(GATE1_PROFILE_FACT_TYPES))}")
    return v


class ProfileFactCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_type: str
    value: Any
    source: Literal["manual", "conversation", "system", "caregiver"] = "manual"
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    @field_validator("fact_type")
    @classmethod
    def validate_fact_type_field(cls, v: str) -> str:
        return _validate_fact_type(v)


class ProfileFactUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Optional[Any] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    verified: Optional[bool] = None

    @field_validator("value")
    @classmethod
    def value_not_empty_when_set(cls, v: Optional[Any]) -> Optional[Any]:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            raise ValueError("value must not be empty")
        return v


class ProfileFactOut(BaseModel):
    id: int
    user_id: int
    fact_type: str
    value: Any
    source: str
    confidence: Optional[float] = None
    verified_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaregiverCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    phone: Optional[str] = Field(None, max_length=32)
    relationship: Optional[str] = Field(None, max_length=64)
    priority: int = 0
    notify_daily_status: bool = False
    notify_emergency: bool = True
    notify_care_summary: bool = False
    notify_vital_alerts: bool = False
    emergency_priority: Optional[int] = Field(None, ge=1)
    can_manage_profile: bool = False
    preferred_language: Optional[Literal["en", "fa", "ar"]] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class CaregiverUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    phone: Optional[str] = Field(None, max_length=32)
    relationship: Optional[str] = Field(None, max_length=64)
    priority: Optional[int] = None
    notify_daily_status: Optional[bool] = None
    notify_emergency: Optional[bool] = None
    notify_care_summary: Optional[bool] = None
    notify_vital_alerts: Optional[bool] = None
    emergency_priority: Optional[int] = Field(None, ge=1)
    can_manage_profile: Optional[bool] = None
    preferred_language: Optional[Literal["en", "fa", "ar"]] = None
    is_active: Optional[bool] = None


class CaregiverOut(BaseModel):
    id: int
    owner_user_id: int
    name: str
    phone: Optional[str] = None
    relationship: Optional[str] = None
    priority: int
    notify_daily_status: bool
    notify_emergency: bool
    notify_care_summary: bool
    notify_vital_alerts: bool
    emergency_priority: Optional[int] = None
    can_manage_profile: bool
    preferred_language: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DependentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=64)
    preferred_language: Literal["en", "fa", "ar"] = "fa"
    birth_year: Optional[int] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = Field(None, max_length=32)
    addressing_preference: Optional[str] = Field(None, max_length=64)
    timezone: Optional[str] = Field(None, max_length=64)
    relationship: Optional[str] = Field(None, max_length=64)
    priority: int = 0


class DependentUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=64)
    preferred_language: Optional[Literal["en", "fa", "ar"]] = None
    birth_year: Optional[int] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = Field(None, max_length=32)
    addressing_preference: Optional[str] = Field(None, max_length=64)
    timezone: Optional[str] = Field(None, max_length=64)
    relationship: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class DependentOut(BaseModel):
    dependent_user_id: int
    account_type: str
    name: Optional[str] = None
    preferred_language: Optional[str] = None
    birth_year: Optional[int] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    addressing_preference: Optional[str] = None
    timezone: Optional[str] = None
    relationship: Optional[str] = None
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
