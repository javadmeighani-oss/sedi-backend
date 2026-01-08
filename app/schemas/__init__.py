# app/schemas/__init__.py
# Export all schemas from package

from .common import APIResponse, ErrorInfo
from .chat import ChatRequest
from .onboarding import OnboardingRequest
from .user import UserCreate, UserResponse
from .health import HealthDataCreate, HealthDataResponse
from .lifestyle import LifestyleDataCreate, LifestyleDataResponse
from .notification import (
    Action,
    NotificationMetadata,
    NotificationCreate,
    NotificationResponse,
    NotificationFeedback
)
from .memory import MemoryCreate, MemoryResponse
from .interaction import InteractionResponse

__all__ = [
    # Common
    "APIResponse",
    "ErrorInfo",
    # Chat
    "ChatRequest",
    # Onboarding
    "OnboardingRequest",
    # User
    "UserCreate",
    "UserResponse",
    # Health
    "HealthDataCreate",
    "HealthDataResponse",
    # Lifestyle
    "LifestyleDataCreate",
    "LifestyleDataResponse",
    # Notification
    "Action",
    "NotificationMetadata",
    "NotificationCreate",
    "NotificationResponse",
    "NotificationFeedback",
    # Memory
    "MemoryCreate",
    "MemoryResponse",
    # Interaction
    "InteractionResponse",
]

