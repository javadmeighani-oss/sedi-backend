# app/services/notification_runtime/__init__.py
"""
Notification Runtime Package (Release B2.1 / Stage 16.6)

This package contains runtime components for notification processing:
- Fallback text generator (language-aware)
- AI enhancement wrapper
- Language resolution helper
- RAGProvider placeholder (future RAG integration)
"""

from backend.app.services.notification_runtime.fallback_generator import generate_fallback_text
from backend.app.services.notification_runtime.ai_enhancer import enhance_with_ai, NOTIF_AI_ENHANCE
from backend.app.services.notification_runtime.language_resolver import resolve_effective_language
from backend.app.services.notification_runtime.rag_provider import RAGProvider
from backend.app.services.notification_runtime.renderer import render
from backend.app.services.notification_runtime.quiet_hours import is_within_quiet_hours

__all__ = [
    "generate_fallback_text",
    "enhance_with_ai",
    "NOTIF_AI_ENHANCE",
    "resolve_effective_language",
    "RAGProvider",
    "render",
    "is_within_quiet_hours",
]
