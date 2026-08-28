"""I9 longitudinal vitals read schemas."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.health_subject import HealthSubjectApiResponse

BucketKindLiteral = Literal["hourly", "daily", "weekly", "calendar_month", "yearly"]


class LongitudinalObservationsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_type: Optional[str] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class LongitudinalAggregatesQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_type: str
    bucket_kind: BucketKindLiteral
    start: datetime
    end: datetime


class LongitudinalEventsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: Optional[datetime] = None
    end: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class AggregateRebuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    measurement_type: str = "heart_rate"
    bucket_kind: BucketKindLiteral = "daily"
    ref: datetime


__all__ = ["HealthSubjectApiResponse"]
