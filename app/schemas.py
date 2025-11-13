# app/schemas.py
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
from datetime import datetime

# ------------------ پایه ------------------
class ErrorInfo(BaseModel):
    code: str
    message: str


class APIResponse(BaseModel):
    ok: bool
    data: Optional[Any] = None
    error: Optional[ErrorInfo] = None


# ------------------ کاربران ------------------
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
        orm_mode = True


# ------------------ داده سلامت ------------------
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

    class Config:
        orm_mode = True


# ------------------ سبک زندگی ------------------
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

    class Config:
        orm_mode = True


# ------------------ نوتیف‌ها ------------------
class NotificationCreate(BaseModel):
    user_id: int
    type: Optional[str] = "info"
    title: Optional[str] = None
    message: str
    tone: Optional[str] = "neutral"
    feedback_options: Optional[List[str]] = []
    language: Optional[str] = "en"


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: str
    title: Optional[str]
    message: str
    tone: Optional[str]
    feedback_options: Optional[List[str]]
    language: str
    is_read: bool
    created_at: datetime

    class Config:
        orm_mode = True


# ------------------ حافظه (Memory) ------------------
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
        orm_mode = True


# ------------------ تعاملات (Chat / GPT) ------------------
class InteractionResponse(BaseModel):
    message: str
    language: str
    user_id: Optional[int] = None
    timestamp: datetime