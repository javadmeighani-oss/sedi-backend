# app/schemas/notification.py
from pydantic import BaseModel, ConfigDict, Field
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
    # Gate 4-B: persisted traceability (effective category/risk resolved in router when null)
    category: Optional[str] = Field(None, description="Gate 4-B notification category")
    source_type: Optional[str] = Field(None, description="Gate 4-B soft source type")
    risk_level: Optional[str] = Field(None, description="Gate 4-B risk level")
    template_key: Optional[str] = Field(None, description="Gate 4-B template key")

    model_config = ConfigDict(from_attributes=True)  # Pydantic V2: renamed from orm_mode


# -------------------- Release B: Notification Contract (B1) --------------------

# Strict contract for notification types
NotificationType = Literal["morning_brief", "connection_ping", "health_alert", "device_disconnected"]
NotificationPriority = Literal["low", "normal", "high", "critical"]


class NotificationPayload(BaseModel):
    """
    Internal payload for notification creation (Release B - Part B1).
    
    This is the strict contract for notification creation that ensures:
    - Deterministic fallback text generation
    - Safe AI enhancement (optional)
    - Stable deduplication
    Allow empty title/body; fallback builder will fill.
    """
    user_id: int = Field(..., description="User ID who will receive the notification")
    type: NotificationType = Field(..., description="Strict notification type: morning_brief | connection_ping | health_alert | device_disconnected")
    title: str = Field(default="", description="Notification title (fallback fills if empty)")
    body: str = Field(default="", description="Notification body/message content (fallback fills if empty)")
    priority: NotificationPriority = Field(default="normal", description="Priority level")
    scheduled_for: Optional[datetime] = Field(None, description="Scheduled datetime for notification")
    dedupe_key: str = Field(..., description="Deterministic deduplication key (format: type:user_id:time_window)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata (e.g. alert_code for health_alert)")
    # Gate 4-B traceability (optional; persist() applies safe defaults when omitted)
    category: Optional[str] = Field(None, description="Gate 4-B category")
    source_type: Optional[str] = Field(None, description="Gate 4-B soft source type")
    source_id: Optional[str] = Field(None, description="Gate 4-B soft source id")
    context: Optional[Dict[str, Any]] = Field(None, description="Gate 4-B allowlisted context (sanitized at persist)")
    risk_level: Optional[str] = Field(None, description="Gate 4-B risk level")
    template_key: Optional[str] = Field(None, description="Gate 4-B template key")


# -------------------- Release B2: Feedback Schema --------------------

class NotificationFeedbackRequest(BaseModel):
    """Standardized feedback request schema (Release B2)"""
    feedback: Literal["positive", "negative", "neutral"] = Field(..., description="Feedback type")
    reason: Optional[str] = Field(None, description="Optional reason for feedback")
    action: Optional[str] = Field(None, description="Optional action (e.g. 'too_early', 'too_late', 'irrelevant')")


# -------------------- V1: Feedback (contract + legacy, normalized event_type) --------------------

FeedbackReactionContract = Literal["seen", "interact", "dismiss", "like", "dislike"]
FeedbackReasonV1 = Literal["too_frequent", "irrelevant", "unclear"]


class FeedbackRequestV1(BaseModel):
    """
    Feedback request body: contract (reaction, timestamp, action_id?, feedback_text?)
    and legacy (feedback, reason, action) and V1 reason enum.
    All fields optional for backward compatibility; validation (e.g. action_id when reaction==interact) in router.
    """
    # Contract Section 5
    reaction: Optional[FeedbackReactionContract] = Field(None, description="Contract: seen | interact | dismiss | like | dislike")
    timestamp: Optional[str] = Field(None, description="Contract: ISO 8601 datetime string")
    action_id: Optional[str] = Field(None, description="Contract: required when reaction is 'interact'")
    feedback_text: Optional[str] = Field(None, description="Contract: optional text")
    # V1 optional reason enum
    reason: Optional[FeedbackReasonV1] = Field(None, description="V1: too_frequent | irrelevant | unclear")
    # Legacy B2 / Stage 16.6 (map into normalized event_type in router)
    feedback: Optional[Literal["positive", "negative", "neutral"]] = Field(None, description="Legacy B2")
    action: Optional[str] = Field(None, description="Legacy: like | dislike | open_chat | dismissed or too_early | too_late | irrelevant")
    client_ts: Optional[str] = Field(None, description="Legacy Stage 16.6 client timestamp")
    meta: Optional[Dict[str, Any]] = Field(None, description="Legacy optional metadata")


# -------------------- Stage 16.6: Push & Feedback Action --------------------

class PushRegisterRequest(BaseModel):
    """Request body for POST /notifications/push/register"""
    user_id: int = Field(..., description="User ID (same auth as existing endpoints)")
    platform: Literal["android"] = Field(..., description="Platform")
    fcm_token: str = Field(..., min_length=1, description="FCM device token")
    device_id: Optional[str] = Field(None, description="Optional device identifier")
    app_version: Optional[str] = Field(None, description="Optional app version")


class PushFeedbackActionRequest(BaseModel):
    """Request body for action-based feedback (like/dislike/open_chat/dismissed)"""
    action: Literal["like", "dislike", "open_chat", "dismissed"] = Field(..., description="Action taken")
    client_ts: Optional[str] = Field(None, description="Client timestamp")
    meta: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")


# -------------------- Stage 16.6.1: Admin Test Push --------------------

class TestPushRequest(BaseModel):
    """Request body for POST /notifications/admin/test_push"""
    user_id: int = Field(..., description="User ID to send test push to")
    channel: Literal["morning", "engagement", "health_alert"] = Field("engagement", description="Push channel")
    title: Optional[str] = Field(None, description="Optional title (default from channel)")
    body: Optional[str] = Field(None, description="Optional body (default from channel)")
    priority: Literal["normal", "high"] = Field("normal", description="Priority")
    ttl_seconds: Optional[int] = Field(3600, description="TTL in seconds")
