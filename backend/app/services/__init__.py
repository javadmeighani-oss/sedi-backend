# app/services/__init__.py
"""
Service Layer - Business Logic

This layer contains business logic and decision-making components.
Routers should delegate to services, not implement business logic directly.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from . import sms_gateway  # noqa: F401 – so patch("backend.app.services.sms_gateway...") works

# Governed lazy package re-exports (Option B): keep package-level compatibility
# without eagerly importing service modules that TOP-import backend.app.models.
# This breaks models → services.i5.enums → services.__init__ → medical → models.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "MedicalService": (".medical", "MedicalService"),
    "DecisionEngine": (".notification_engine", "DecisionEngine"),
    "NotificationBuilder": (".notification_engine", "NotificationBuilder"),
    "TimingRules": (".notification_engine", "TimingRules"),
    "RAGService": (".rag", "RAGService"),
    "UserContextService": (".user_context", "UserContextService"),
    "UserContextPack": (".user_context", "UserContextPack"),
}

__all__ = [
    "MedicalService",
    "DecisionEngine",
    "NotificationBuilder",
    "TimingRules",
    "RAGService",
    "UserContextService",
    "UserContextPack",
]

if TYPE_CHECKING:
    from .medical import MedicalService
    from .notification_engine import DecisionEngine, NotificationBuilder, TimingRules
    from .rag import RAGService
    from .user_context import UserContextPack, UserContextService


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = importlib.import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
