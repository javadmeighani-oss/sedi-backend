# backend.app.services.notification_runtime.user_context_adapter
"""
Stage 23 Step 4: Lightweight adapter to build a small notification context from UserContextPack.
Fail-open: on any failure returns {} and logs with [NotifContext].
"""

import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from backend.app.services.user_context import UserContextService

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

        pack = UserContextService(db).get_user_context(user_id)
        if pack is None:
            return {}

        goals = getattr(pack, "goals", None)
        goals_items: List[str] = []
        if goals and getattr(goals, "items", None):
            raw = list(goals.items) if isinstance(goals.items, list) else []
            goals_items = [str(x).strip() for x in raw if x][:5]

        lifestyle = getattr(pack, "lifestyle", None)
        lifestyle_text = ""
        if lifestyle and getattr(lifestyle, "text", None) and str(lifestyle.text).strip():
            lifestyle_text = str(lifestyle.text).strip()[:200]

        daily = getattr(pack, "daily_memory_summary", None)
        daily_memory_summary = ""
        if daily and str(daily).strip():
            daily_memory_summary = str(daily).strip()[:150]

        out = {
            "preferred_name": (getattr(pack, "preferred_name", None) or "").strip() or None,
            "language": (getattr(pack, "language", None) or "").strip() or None,
            "timezone": (getattr(pack, "timezone", None) or "").strip() or None,
            "goals_items": goals_items,
            "lifestyle_text": lifestyle_text,
            "daily_memory_summary": daily_memory_summary,
        }
        logger.debug("%s built context for user_id=%s preferred_name=%s", _LOG_PREFIX, user_id, out.get("preferred_name"))
        return out
    except Exception as e:
        logger.debug("%s build failed for user_id=%s: %s", _LOG_PREFIX, user_id, e)
        return {}
