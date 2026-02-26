# app/schemas/health.py
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class HealthDataCreate(BaseModel):
    user_id: int
    heart_rate: Optional[float] = None
    temperature: Optional[float] = None
    spo2: Optional[float] = None


class HealthDataResponse(BaseModel):
    id: int
    user_id: int
    heart_rate: Optional[float]
    temperature: Optional[float]
    spo2: Optional[float]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  # Pydantic V2: renamed from orm_mode
