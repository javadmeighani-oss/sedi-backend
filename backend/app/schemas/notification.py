# app/schemas/notification.py
from pydantic import BaseModel, Field
from typing import Optional
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
