# app/schemas/notification.py
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any
from datetime import datetime


# Base schema with common fields
class NotificationBase(BaseModel):
    """Base notification schema with common fields"""
    type: str = Field(..., description="Notification type (e.g. HEALTH, REMINDER, INSIGHT)")
    title: Optional[str] = Field(None, description="Notification title")
    body: str = Field(..., min_length=1, description="Notification body/message content")
    priority: str = Field(default="normal", description="Priority level: low | normal | high | critical")
    scheduled_for: Optional[datetime] = Field(None, description="Scheduled datetime for notification (for scheduler integration)")


# Schema for creating notifications
class NotificationCreate(NotificationBase):
    """Schema for creating a new notification"""
    user_id: int = Field(..., description="User ID who will receive the notification")


# Schema for notification responses
class NotificationResponse(NotificationBase):
    """Schema for notification API responses"""
    id: int
    user_id: int
    is_read: bool
    is_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic V2: renamed from orm_mode


# -------------------- Release B: Notification Contract (B1) --------------------

# Strict contract for 3 notification types
NotificationType = Literal["morning_brief", "connection_ping", "health_alert"]
NotificationPriority = Literal["low", "normal", "high", "critical"]


class NotificationPayload(BaseModel):
    """
    Internal payload for notification creation (Release B - Part B1).
    
    This is the strict contract for notification creation that ensures:
    - Deterministic fallback text generation
    - Safe AI enhancement (optional)
    - Stable deduplication
    """
    user_id: int = Field(..., description="User ID who will receive the notification")
    type: NotificationType = Field(..., description="Strict notification type: morning_brief | connection_ping | health_alert")
    title: str = Field(..., min_length=1, description="Notification title")
    body: str = Field(..., min_length=1, description="Notification body/message content")
    priority: NotificationPriority = Field(default="normal", description="Priority level")
    scheduled_for: Optional[datetime] = Field(None, description="Scheduled datetime for notification")
    dedupe_key: str = Field(..., description="Deterministic deduplication key (format: type:user_id:time_window)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata (e.g. alert_code for health_alert)")


# -------------------- Release B2: Feedback Schema --------------------

class NotificationFeedbackRequest(BaseModel):
    """Standardized feedback request schema (Release B2)"""
    feedback: Literal["positive", "negative", "neutral"] = Field(..., description="Feedback type")
    reason: Optional[str] = Field(None, description="Optional reason for feedback")
    action: Optional[str] = Field(None, description="Optional action (e.g. 'too_early', 'too_late', 'irrelevant')")
