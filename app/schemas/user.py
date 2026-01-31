# app/schemas/user.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    passkey: Optional[str] = None
    preferred_language: Optional[str] = "en"


class UserResponse(BaseModel):
    id: int
    name: str
    preferred_language: str
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic V2: renamed from orm_mode
