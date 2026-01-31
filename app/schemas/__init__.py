# app/schemas/__init__.py
# Export all schemas from package

from .common import APIResponse, ErrorInfo
from .chat import ChatRequest
from .onboarding import OnboardingRequest
from .user import UserCreate, UserResponse
from .health import HealthDataCreate, HealthDataResponse
from .lifestyle import LifestyleDataCreate, LifestyleDataResponse
from .notification import (
    NotificationBase,
    NotificationCreate,
    NotificationResponse
)
from .memory import MemoryCreate, MemoryResponse
from .interaction import InteractionResponse
from .medical import (
    MedicalConditionBase,
    MedicalConditionCreate,
    MedicalConditionResponse,
    MedicationBase,
    MedicationCreate,
    MedicationResponse,
    UserConditionBase,
    UserConditionCreate,
    UserConditionResponse
)

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
    "NotificationBase",
    "NotificationCreate",
    "NotificationResponse",
    # Memory
    "MemoryCreate",
    "MemoryResponse",
    # Interaction
    "InteractionResponse",
    # Medical
    "MedicalConditionBase",
    "MedicalConditionCreate",
    "MedicalConditionResponse",
    "MedicationBase",
    "MedicationCreate",
    "MedicationResponse",
    "UserConditionBase",
    "UserConditionCreate",
    "UserConditionResponse",
]

