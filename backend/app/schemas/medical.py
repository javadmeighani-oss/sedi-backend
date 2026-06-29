# app/schemas/medical.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime


# -------------------- MedicalCondition Schemas --------------------
class MedicalConditionBase(BaseModel):
    """Base schema for medical condition"""
    name: str = Field(..., min_length=1, description="Condition name (e.g. 'Diabetes Type 2')")
    description: Optional[str] = Field(None, description="Brief description of the condition")
    category: Optional[str] = Field(None, description="Condition category (e.g. 'chronic', 'cardiovascular')")
    embedding_id: Optional[str] = Field(None, description="RAG embedding ID (optional, for future RAG integration)")


class MedicalConditionCreate(MedicalConditionBase):
    """Schema for creating a medical condition"""
    pass


class MedicalConditionResponse(MedicalConditionBase):
    """Schema for medical condition API responses"""
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -------------------- Medication Schemas --------------------
class MedicationBase(BaseModel):
    """Base schema for medication"""
    name: str = Field(..., min_length=1, description="Medication name")
    generic_name: Optional[str] = Field(None, description="Generic name if available")
    dosage_form: Optional[str] = Field(None, description="Dosage form (e.g. 'tablet', 'capsule')")
    default_dosage: Optional[str] = Field(None, description="Default dosage (e.g. '500mg', '10ml')")
    embedding_id: Optional[str] = Field(None, description="RAG embedding ID (optional, for future RAG integration)")


class MedicationCreate(MedicationBase):
    """Schema for creating a medication"""
    pass


class MedicationResponse(MedicationBase):
    """Schema for medication API responses"""
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# -------------------- UserCondition Schemas --------------------
class UserConditionBase(BaseModel):
    """Base schema for user condition assignment"""
    condition_id: int = Field(..., description="Medical condition ID")
    diagnosed_date: Optional[datetime] = Field(None, description="When condition was diagnosed")
    severity: Optional[str] = Field(None, description="Severity level (e.g. 'mild', 'moderate', 'severe')")
    notes: Optional[str] = Field(None, description="Additional notes about user's condition")
    embedding_id: Optional[str] = Field(None, description="RAG embedding ID (optional, for future RAG integration)")


class UserConditionAssignRequest(UserConditionBase):
    """POST /conditions/assign body (authenticated user only; no user_id)."""

    model_config = ConfigDict(extra="forbid")


class UserConditionCreate(UserConditionBase):
    """Legacy schema for creating a user condition assignment (includes user_id)."""
    user_id: int = Field(..., description="User ID")


class UserConditionResponse(UserConditionBase):
    """Schema for user condition API responses"""
    id: int
    user_id: int
    created_at: datetime
    condition: Optional[MedicalConditionResponse] = Field(None, description="Associated medical condition details")

    model_config = ConfigDict(from_attributes=True)


# -------------------- UserMedication API (Phase V1.1B) --------------------
USER_DOSAGE_MAX = 128
INSTRUCTIONS_MAX = 2000
MEDICATION_NAME_MAX = 255
TIMEZONE_MAX = 64
INTERVAL_HOURS_MIN = 1
INTERVAL_HOURS_MAX = 24
MAX_REMINDER_TIMES = 12


class UserMedicationCreateIn(BaseModel):
    """POST /user/medications — authenticated user only."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=MEDICATION_NAME_MAX)
    generic_name: Optional[str] = Field(None, max_length=MEDICATION_NAME_MAX)
    dosage_form: Optional[str] = Field(None, max_length=64)
    user_dosage: Optional[str] = Field(None, max_length=USER_DOSAGE_MAX)
    instructions: Optional[str] = Field(None, max_length=INSTRUCTIONS_MAX)
    reminder_enabled: bool = True
    timezone: Optional[str] = Field(None, max_length=TIMEZONE_MAX)
    reminder_times: Optional[list[str]] = Field(None, max_length=MAX_REMINDER_TIMES)
    interval_hours: Optional[int] = Field(None, ge=INTERVAL_HOURS_MIN, le=INTERVAL_HOURS_MAX)


class UserMedicationUpdateIn(BaseModel):
    """PATCH /user/medications/{id} — partial update."""

    model_config = ConfigDict(extra="forbid")

    user_dosage: Optional[str] = Field(None, max_length=USER_DOSAGE_MAX)
    instructions: Optional[str] = Field(None, max_length=INSTRUCTIONS_MAX)
    reminder_enabled: Optional[bool] = None
    timezone: Optional[str] = Field(None, max_length=TIMEZONE_MAX)
    reminder_times: Optional[list[str]] = Field(None, max_length=MAX_REMINDER_TIMES)
    interval_hours: Optional[int] = Field(None, ge=INTERVAL_HOURS_MIN, le=INTERVAL_HOURS_MAX)


class UserMedicationOut(BaseModel):
    """User medication assignment with schedule times."""

    id: int
    medication_id: int
    name: str
    generic_name: Optional[str] = None
    dosage_form: Optional[str] = None
    user_dosage: Optional[str] = None
    instructions: Optional[str] = None
    reminder_enabled: bool
    timezone: Optional[str] = None
    reminder_times: list[str] = Field(default_factory=list)
    interval_hours: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

