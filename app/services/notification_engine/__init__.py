# app/services/notification_engine/__init__.py
"""
Notification Engine Package (Release B - Part B1)

Exports:
- NotificationBuilder: Builds notification objects
- DecisionEngine: Determines when and what notifications to create
- TimingRules: Manages notification timing
- Fallback generator and AI enhancer
"""

from app.services.notification_engine import (
    NotificationBuilder,
    DecisionEngine,
    TimingRules
)

from app.services.notification_engine.fallback_generator import generate_fallback_text
from app.services.notification_engine.ai_enhancer import enhance_with_ai, NOTIF_AI_ENHANCE

__all__ = [
    "NotificationBuilder",
    "DecisionEngine",
    "TimingRules",
    "generate_fallback_text",
    "enhance_with_ai",
    "NOTIF_AI_ENHANCE",
]
