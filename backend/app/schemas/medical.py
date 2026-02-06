# app/schemas/medical.py
from pydantic import BaseModel, Field
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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


# -------------------- UserCondition Schemas --------------------
class UserConditionBase(BaseModel):
    """Base schema for user condition assignment"""
    condition_id: int = Field(..., description="Medical condition ID")
    diagnosed_date: Optional[datetime] = Field(None, description="When condition was diagnosed")
    severity: Optional[str] = Field(None, description="Severity level (e.g. 'mild', 'moderate', 'severe')")
    notes: Optional[str] = Field(None, description="Additional notes about user's condition")
    embedding_id: Optional[str] = Field(None, description="RAG embedding ID (optional, for future RAG integration)")


class UserConditionCreate(UserConditionBase):
    """Schema for creating a user condition assignment"""
    user_id: int = Field(..., description="User ID")


class UserConditionResponse(UserConditionBase):
    """Schema for user condition API responses"""
    id: int
    user_id: int
    created_at: datetime
    condition: Optional[MedicalConditionResponse] = Field(None, description="Associated medical condition details")

    class Config:
        from_attributes = True
