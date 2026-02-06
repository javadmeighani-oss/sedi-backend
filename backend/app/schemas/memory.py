# app/schemas/memory.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MemoryCreate(BaseModel):
    user_id: int
    summary: Optional[str] = None
    mood: Optional[str] = "neutral"
    context: Optional[str] = "chat"


class MemoryResponse(BaseModel):
    id: int
    user_id: int
    summary: Optional[str]
    mood: Optional[str]
    context: Optional[str]
    created_at: datetime
    last_interaction: datetime

    class Config:
        from_attributes = True  # Pydantic V2: renamed from orm_mode
