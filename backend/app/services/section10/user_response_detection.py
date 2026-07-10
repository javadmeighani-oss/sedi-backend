"""User response detection for escalation — approved interaction signals only."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.core.conversation.memory import ConversationMemory


def user_has_meaningful_response(
    db: Session,
    user_id: int,
    *,
    since: Optional[datetime] = None,
    grace_minutes: int = 0,
) -> bool:
    """Detect user response via chat, notification feedback, or notification-originated chat."""
    threshold = since
    if threshold is not None and grace_minutes > 0:
        threshold = threshold - timedelta(minutes=grace_minutes)

    memory = ConversationMemory(db)
    last_chat = memory.get_last_interaction_time(user_id)
    if last_chat is not None and (threshold is None or last_chat >= threshold):
        return True

    q = db.query(models.InteractionEvent).filter(models.InteractionEvent.user_id == user_id)
    if threshold is not None:
        q = q.filter(models.InteractionEvent.created_at >= threshold)
    event = (
        q.filter(
            models.InteractionEvent.event_type.in_(
                ["CHAT_MESSAGE", "NOTIFICATION_FEEDBACK", "OPEN_CHAT"]
            )
        )
        .order_by(models.InteractionEvent.created_at.desc())
        .first()
    )
    return event is not None
