"""I9 Health Subject schemas."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ManagedHealthSubjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(..., min_length=1, max_length=255)
    access_role: Literal["CAREGIVER", "MANAGER"] = Field(default="MANAGER")
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=128)


class ManagedHealthSubjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)


class HealthSubjectConditionReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition_id: int = Field(..., ge=1)
    severity: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)
    diagnosed_date: Optional[datetime] = None


class HealthSubjectResponse(BaseModel):
    id: int
    display_name: Optional[str] = None
    linked_user_id: Optional[int] = None
    subject_kind: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HealthSubjectApiResponse(BaseModel):
    ok: bool
    data: Optional[dict] = None
    error: Optional[dict] = None


class DeviceRebindRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    health_subject_id: int = Field(..., description="Target health subject for device binding")
