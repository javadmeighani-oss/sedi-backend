# app/schemas/notification.py
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json

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
