# app/schemas.py
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
from datetime import datetime
import json

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
        from_attributes = True  # Pydantic V2: renamed from orm_mode


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
        from_attributes = True  # Pydantic V2: renamed from orm_mode


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
        from_attributes = True  # Pydantic V2: renamed from orm_mode


# ------------------ نوتیف‌ها (Contract-Compliant) ------------------

# Action object (Section 4 of contract)
class Action(BaseModel):
    id: str
    label: str
    type: str  # "quick_reply" | "navigate" | "dismiss" | "custom"
    payload: Optional[Dict[str, Any]] = None


# Metadata object (Section 6 of contract)
class NotificationMetadata(BaseModel):
    language: Optional[str] = None  # ISO 639-1
    tone: Optional[str] = None
    context: Optional[str] = None
    source: Optional[str] = None


# Notification Create (for internal use)
class NotificationCreate(BaseModel):
    user_id: int
    type: str = "info"  # Contract enum: info, alert, reminder, check_in, achievement
    priority: str = "normal"  # Contract enum: low, normal, high, urgent
    title: Optional[str] = None
    message: str
    actions: Optional[List[Action]] = []
    metadata: Optional[NotificationMetadata] = None


# Notification Response (Contract Section 1)
class NotificationResponse(BaseModel):
    id: str  # Contract: string (can be int converted to string)
    type: str  # Contract enum
    priority: str  # Contract enum
    title: Optional[str] = None
    message: str
    actions: Optional[List[Action]] = []
    metadata: Optional[NotificationMetadata] = None
    created_at: str  # ISO 8601 datetime string
    is_read: bool

    class Config:
        from_attributes = True  # Pydantic V2: renamed from orm_mode

    @classmethod
    def from_orm(cls, obj):
        """Convert ORM object to contract-compliant response"""
        # Parse JSON strings from database
        actions_list = []
        if obj.actions:
            try:
                actions_data = json.loads(obj.actions)
                actions_list = [Action(**a) for a in actions_data]
            except:
                actions_list = []

        metadata_obj = None
        if obj.metadata_json:
            try:
                metadata_data = json.loads(obj.metadata_json)
                metadata_obj = NotificationMetadata(**metadata_data)
            except:
                metadata_obj = None

        return cls(
            id=str(obj.id),
            type=obj.type,
            priority=obj.priority,
            title=obj.title,
            message=obj.message,
            actions=actions_list,
            metadata=metadata_obj,
            created_at=obj.created_at.isoformat(),
            is_read=obj.is_read
        )


# Feedback Payload (Contract Section 5)
class NotificationFeedback(BaseModel):
    notification_id: str
    action_id: Optional[str] = None
    reaction: str  # Contract enum: seen, interact, dismiss, like, dislike
    feedback_text: Optional[str] = None
    timestamp: str  # ISO 8601 datetime string


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
        from_attributes = True  # Pydantic V2: renamed from orm_mode


# ------------------ تعاملات (Chat / GPT) ------------------
class InteractionResponse(BaseModel):
    message: str
    language: str
    user_id: Optional[int] = None
    timestamp: datetime
    requires_security_check: Optional[bool] = False  # Flag for suspicious behavior detection