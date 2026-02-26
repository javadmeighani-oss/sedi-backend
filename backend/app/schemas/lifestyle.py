# app/schemas/lifestyle.py
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class LifestyleDataCreate(BaseModel):
    user_id: int
    sleep_hours: Optional[float] = None
    steps: Optional[int] = None
    calories: Optional[float] = None
    stress_level: Optional[int] = None


class LifestyleDataResponse(BaseModel):
    id: int
    user_id: int
    sleep_hours: Optional[float]
    steps: Optional[int]
    calories: Optional[float]
    stress_level: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)  # Pydantic V2: renamed from orm_mode
