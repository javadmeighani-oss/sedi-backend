"""AUTH session persistence + 30-day re-auth. Consumes existing presence evidence only."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models

logger = logging.getLogger(__name__)

SECURITY_REAUTH_DAYS = 30
AUTH_LOGIN_EVENT_TYPE = "auth_login_success"
SESSION_OPEN_EVENT_TYPE = "session_open"
AUTH_FOREGROUND_EVENT_TYPES = frozenset({AUTH_LOGIN_EVENT_TYPE, SESSION_OPEN_EVENT_TYPE})


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record_auth_login_presence(db: Session, user_id: int) -> None:
    """LOGIN/REGISTRATION token issue is trusted current presence. Existing ledger only."""
    from backend.app.services.gate4.interaction_event_service import create_interaction_event

    create_interaction_event(
        db,
        user_id=user_id,
        event_type=AUTH_LOGIN_EVENT_TYPE,
        source="system",
        metadata={"authority": "AUTH", "presence": True},
    )


def record_session_open_presence(db: Session, user_id: int) -> None:
    """Authenticated session/open is foreground presence. Existing ledger only."""
    from backend.app.services.gate4.interaction_event_service import create_interaction_event

    create_interaction_event(
        db,
        user_id=user_id,
        event_type=SESSION_OPEN_EVENT_TYPE,
        source="system",
        metadata={"authority": "A3_SESSION_OPEN", "presence": True},
    )


def _last_auth_foreground_at(db: Session, user_id: int) -> Optional[datetime]:
    row = (
        db.query(models.InteractionEvent.created_at)
        .filter(
            models.InteractionEvent.user_id == user_id,
            models.InteractionEvent.event_type.in_(tuple(AUTH_FOREGROUND_EVENT_TYPES)),
        )
        .order_by(models.InteractionEvent.created_at.desc())
        .first()
    )
    return row[0] if row else None


def get_last_meaningful_user_presence_at(db: Session, user_id: int) -> Optional[datetime]:
    """AUTH consumer: chat Memory + explicit notification actions + login/session-open."""
    from backend.app.services.i10.interaction_recorder import (
        get_last_chat_activity_at,
        get_last_notification_presence_at,
    )

    candidates = [
        ts
        for ts in (
            get_last_chat_activity_at(db, user_id),
            get_last_notification_presence_at(db, user_id),
            _last_auth_foreground_at(db, user_id),
        )
        if ts is not None
    ]
    if not candidates:
        return None
    return max(candidates)


def refresh_allowed_for_presence(db: Session, user_id: int, *, when: Optional[datetime] = None) -> bool:
    """
    True when refresh may proceed. Fail-open on lookup errors so infrastructure
    faults are not converted into a security logout.
    """
    try:
        last = get_last_meaningful_user_presence_at(db, user_id)
        if last is None:
            return True
        last_aware = _as_utc(last)
        now = _as_utc(when) or _now()
        return (now - last_aware) < timedelta(days=SECURITY_REAUTH_DAYS)
    except Exception:
        logger.exception("[AUTH] presence lookup failed; allowing refresh fail-open user=%s", user_id)
        return True
