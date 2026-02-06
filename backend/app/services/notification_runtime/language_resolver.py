# app/services/notification_runtime/language_resolver.py
"""
Language Resolution Helper (Release B2.1)

Resolves effective language for notifications using strict priority:
1. user.preferred_language
2. memory_context.preferred_language (if exists)
3. fallback → "en"

Supported languages: en, fa, ar
"""

from typing import Optional, Literal
from sqlalchemy.orm import Session

from app.models import User
from app.services.memory.memory_context import MemoryContext

SupportedLanguage = Literal["en", "fa", "ar"]


def resolve_effective_language(
    db: Session,
    user_id: int,
    memory_context: Optional[MemoryContext] = None
) -> SupportedLanguage:
    """
    Resolve effective language for a user (Release B2.1).
    
    Priority order:
    1. user.preferred_language (from User model)
    2. memory_context.preferred_language (if MemoryContext has this field)
    3. fallback → "en"
    
    Args:
        db: Database session
        user_id: User ID
        memory_context: Optional MemoryContext (may contain preferred_language)
    
    Returns:
        Effective language code: "en" | "fa" | "ar" (default: "en")
    """
    # Priority 1: User profile language
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.preferred_language:
        lang = user.preferred_language.lower()
        if lang in ("en", "fa", "ar"):
            return lang
    
    # Priority 2: Memory context preferred_language (if MemoryContext supports it)
    # Note: Current MemoryContext doesn't have preferred_language field
    # This is a placeholder for future enhancement
    if memory_context and hasattr(memory_context, "preferred_language"):
        lang = memory_context.preferred_language
        if lang and lang.lower() in ("en", "fa", "ar"):
            return lang.lower()
    
    # Priority 3: Default fallback
    return "en"
