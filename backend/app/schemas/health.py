# app/schemas/health.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime


class HealthDataCreate(BaseModel):
    """Legacy create schema (includes user_id). Prefer HealthDataAddRequest for API."""

    user_id: int
    heart_rate: Optional[float] = None
    temperature: Optional[float] = None
    spo2: Optional[float] = None


class HealthDataAddRequest(BaseModel):
    """Authenticated health vitals add (no user_id; identity from JWT)."""

    model_config = ConfigDict(extra="forbid")

    heart_rate: Optional[float] = Field(None, description="Heart rate (bpm)")
    temperature: Optional[float] = Field(None, description="Body temperature (°C)")
    spo2: Optional[float] = Field(None, ge=0, le=100, description="Blood oxygen saturation (%)")


class HealthDataResponse(BaseModel):
    id: int
    user_id: int
    heart_rate: Optional[float]
    temperature: Optional[float]
    spo2: Optional[float]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  # Pydantic V2: renamed from orm_mode
