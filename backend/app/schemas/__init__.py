# app/schemas/__init__.py
# Export all schemas from package

from .common import APIResponse, ErrorInfo
from .chat import ChatRequest
from .onboarding import OnboardingRequest
from .user import UserCreate, UserResponse
from .user_knowledge import (
    UserProfileKnowledgeRead,
    UserProfileKnowledgeUpsert,
    UserFactRead,
    UserFactUpsert,
)
from .health import HealthDataCreate, HealthDataResponse
from .lifestyle import LifestyleDataCreate, LifestyleDataResponse
from .notification import (
    NotificationBase,
    NotificationCreate,
    NotificationResponse
)
from .memory import (
    MemoryCreate,
    MemoryResponse,
    HistoryResponse,
    HistoryGroupItem,
    HistoryTurnItem,
)
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
from .device import (
    DeviceIngestRequest,
    DeviceIngestResponse,
    DeviceEventResponse
)
from .devices import (
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    DevicePublicInfo,
    DevicesListResponse,
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
    # User Knowledge
    "UserProfileKnowledgeRead",
    "UserProfileKnowledgeUpsert",
    "UserFactRead",
    "UserFactUpsert",
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
    "HistoryResponse",
    "HistoryGroupItem",
    "HistoryTurnItem",
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
    # Device
    "DeviceIngestRequest",
    "DeviceIngestResponse",
    "DeviceEventResponse",
    # Devices (identity)
    "DeviceRegisterRequest",
    "DeviceRegisterResponse",
    "DevicePublicInfo",
    "DevicesListResponse",
]

