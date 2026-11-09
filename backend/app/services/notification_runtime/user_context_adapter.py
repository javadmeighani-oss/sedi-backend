# backend.app.services.notification_runtime.user_context_adapter
"""
Stage 23 Step 4: Lightweight adapter to build a small notification context from UserContextPack.
Fail-open: on any failure returns {} and logs with [NotifContext].
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.app.services.user_context import UserContextService
from backend.app.services.user_context.user_state import user_state_from_pack

logger = logging.getLogger(__name__)
_LOG_PREFIX = "[NotifContext]"


def build_notification_context(db: Session, user_id: int) -> Dict[str, Any]:
    """
    Build a small dict for notification personalization from UserContextPack.

    Returns:
        preferred_name, language, timezone,
        goals_items (list, max 5),
        lifestyle_text (str, max 200 chars),
        daily_memory_summary (str, max 150 chars)
    On any failure returns {}.
    """
    try:

        # R-074 step 5a: the shared UserState contract (same normalisation as chat, profile and session open).
        state = user_state_from_pack(UserContextService(db).get_user_context(user_id))
        if state is None:
            return {}

        out = {
            "preferred_name": state.preferred_name,
            "language": state.language_raw,
            "timezone": state.timezone,
            "goals_items": list(state.goals),
            "lifestyle_text": state.lifestyle_text,
            "daily_memory_summary": state.daily_summary,
        }
        logger.debug("%s built context for user_id=%s preferred_name=%s", _LOG_PREFIX, user_id, out.get("preferred_name"))
        return out
    except Exception as e:
        logger.debug("%s build failed for user_id=%s: %s", _LOG_PREFIX, user_id, e)
        return {}
