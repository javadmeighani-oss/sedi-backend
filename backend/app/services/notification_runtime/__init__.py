# app/services/notification_runtime/__init__.py
"""
Notification Runtime Package (Release B2.1)

This package contains runtime components for notification processing:
- Fallback text generator (language-aware)
- AI enhancement wrapper
- Language resolution helper

Note: This package is imported by app/services/notification_engine.py (the main module).
"""

from backend.app.services.notification_runtime.fallback_generator import generate_fallback_text
from backend.app.services.notification_runtime.ai_enhancer import enhance_with_ai, NOTIF_AI_ENHANCE
from backend.app.services.notification_runtime.language_resolver import resolve_effective_language

__all__ = [
    "generate_fallback_text",
    "enhance_with_ai",
    "NOTIF_AI_ENHANCE",
    "resolve_effective_language",
]
