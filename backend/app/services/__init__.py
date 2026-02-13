# app/services/__init__.py
"""
Service Layer - Business Logic

This layer contains business logic and decision-making components.
Routers should delegate to services, not implement business logic directly.
"""

from .medical import MedicalService
from .notification_engine import DecisionEngine, NotificationBuilder, TimingRules
from .rag import RAGService
from .user_context import UserContextService, UserContextPack

__all__ = [
    "MedicalService",
    "DecisionEngine",
    "NotificationBuilder",
    "TimingRules",
    "RAGService",
    "UserContextService",
    "UserContextPack",
]
