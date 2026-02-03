# app/services/notification_runtime/__init__.py
"""
Notification Runtime Package (Release B - Part B1)

This package contains runtime components for notification processing:
- Fallback text generator
- AI enhancement wrapper

Note: This package is imported by app/services/notification_engine.py (the main module).
"""

from app.services.notification_runtime.fallback_generator import generate_fallback_text
from app.services.notification_runtime.ai_enhancer import enhance_with_ai, NOTIF_AI_ENHANCE

__all__ = [
    "generate_fallback_text",
    "enhance_with_ai",
    "NOTIF_AI_ENHANCE",
]
