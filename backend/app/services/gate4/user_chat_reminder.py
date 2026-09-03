"""
Gate 4E — User-created reminders from explicit chat requests.

Parses explicit reminder intent, creates a UserEvent, and schedules a safe
non-clinical reminder notification. No dosage or medication-change advice.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytz
from sqlalchemy.orm import Session

from backend.app.models import User, UserProfileCore
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate2_data_service import create_event
from backend.app.services.gate4.notification_context import NotificationSourceType
from backend.app.services.gate4.policy_prefs_bridge import resolve_user_timezone
from backend.app.services.memory import MemoryRepository

logger = logging.getLogger(__name__)

_REMINDER_PATTERNS = (
    re.compile(
        r"(?:tomorrow|today)\s+at\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{1,2}))?\s*(?P<body>.+)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:فردا|پس\s*فردا|امروز)\s+ساعت\s+(?P<hour>\d{1,2})(?:[:٫.](?P<minute>\d{1,2}))?\s*(?P<body>.+)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:remind\s+me|set\s+a?\s*reminder|remember\s+to)\s+(?:at\s+)?(?P<body>.+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:یادم\s+بنداز|یادآوری\s+کن|یادآور\s+بذار|یادآور\s+بزار)\s*(?P<body>.+)?",
        re.IGNORECASE,
    ),
)

_FORBIDDEN_ADVICE = re.compile(
    r"(change\s+(?:your\s+)?(?:dose|dosage|medication)|"
    r"increase\s+(?:my\s+)?(?:medication\s+)?dose|decrease\s+(?:my\s+)?(?:medication\s+)?dose|"
    r"دوز|تغییر\s+دارو|افزایش\s+دوز|کاهش\s+دوز)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ChatReminderParseResult:
    is_reminder_request: bool
    needs_clarification: bool
    clarification_message: Optional[str] = None
    reminder_title: Optional[str] = None
    scheduled_at_utc: Optional[datetime] = None
    timezone: Optional[str] = None


def _load_timezone(db: Session, user_id: int) -> str:
    profile = db.query(UserProfileCore).filter(UserProfileCore.user_id == user_id).first()
    user = db.query(User).filter(User.id == user_id).first()
    memory_tz = None
    try:
        repo = MemoryRepository(db)
        fact = repo.get_fact(user_id=user_id, domain="preferences", key="timezone")
        if fact and fact.value_json:
            data = json.loads(fact.value_json)
            memory_tz = data.get("tz") if isinstance(data, dict) else data
    except Exception:
        pass
    return resolve_user_timezone(user=user, profile_core=profile, memory_timezone=memory_tz)


def _local_to_utc(local_dt: datetime, tz_name: str) -> datetime:
    try:
        tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        tz = pytz.timezone("Asia/Tehran")
    if local_dt.tzinfo is None:
        localized = tz.localize(local_dt)
    else:
        localized = local_dt.astimezone(tz)
    return localized.astimezone(timezone.utc)


def parse_chat_reminder_request(
    message: str,
    *,
    now_utc: datetime | None = None,
    user_timezone: str = "Asia/Tehran",
) -> ChatReminderParseResult:
    """Detect explicit reminder intent and parse a safe schedule when possible."""
    text = (message or "").strip()
    if not text:
        return ChatReminderParseResult(False, False)

    if _FORBIDDEN_ADVICE.search(text):
        return ChatReminderParseResult(
            is_reminder_request=True,
            needs_clarification=True,
            clarification_message=(
                "I can set a general reminder, but I cannot advise on medication dosage or changes. "
                "Please ask your clinician about dose changes."
            ),
        )

    has_reminder_intent = bool(
        re.search(
            r"(remind\s+me|set\s+a?\s*reminder|remember\s+to|یادم\s+بنداز|یادآوری|tomorrow\s+at|فردا\s+ساعت)",
            text,
            re.IGNORECASE,
        )
    )
    if not has_reminder_intent:
        return ChatReminderParseResult(False, False)

    effective_now = now_utc or datetime.now(timezone.utc)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=timezone.utc)

    for pattern in _REMINDER_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        groups = match.groupdict()
        body = (groups.get("body") or "").strip(" .،،")
        hour_raw = groups.get("hour")
        minute_raw = groups.get("minute") or "0"

        if hour_raw is not None:
            try:
                hour = int(hour_raw)
                minute = int(minute_raw)
                if hour < 0 or hour > 23 or minute < 0 or minute > 59:
                    raise ValueError("invalid time")
            except ValueError:
                return ChatReminderParseResult(
                    is_reminder_request=True,
                    needs_clarification=True,
                    clarification_message="I could not understand the time. Please use a clear time like 10:00.",
                )

            try:
                tz = pytz.timezone(user_timezone)
            except pytz.exceptions.UnknownTimeZoneError:
                tz = pytz.timezone("Asia/Tehran")
            now_local = effective_now.astimezone(tz)
            target_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if "فردا" in text or "tomorrow" in text.lower() or "today" in text.lower():
                target_local = target_local + timedelta(days=1)
            elif target_local <= now_local:
                target_local = target_local + timedelta(days=1)

            title = body[:120] if body else "Reminder"
            return ChatReminderParseResult(
                is_reminder_request=True,
                needs_clarification=False,
                reminder_title=title,
                scheduled_at_utc=_local_to_utc(target_local.replace(tzinfo=None), user_timezone),
                timezone=user_timezone,
            )

        if body:
            return ChatReminderParseResult(
                is_reminder_request=True,
                needs_clarification=True,
                clarification_message=(
                    "When should I remind you? Please include a date and time, for example: "
                    "'tomorrow at 10:00 remind me to take my medication'."
                ),
            )

    return ChatReminderParseResult(False, False)


def create_user_chat_reminder(
    db: Session,
    *,
    user_id: int,
    message: str,
    conversation_id: Optional[str] = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """
    Parse message and create user event + scheduled reminder notification when safe.

    Returns summary dict; never raises for malformed input.
    """
    tz_name = _load_timezone(db, user_id)
    parsed = parse_chat_reminder_request(
        message, now_utc=now_utc, user_timezone=tz_name
    )
    if not parsed.is_reminder_request:
        return {"created": False, "reason": "not_a_reminder_request"}
    if parsed.needs_clarification:
        return {
            "created": False,
            "reason": "needs_clarification",
            "clarification_message": parsed.clarification_message,
        }
    if not parsed.scheduled_at_utc or not parsed.reminder_title:
        return {"created": False, "reason": "incomplete_parse"}

    scheduled_naive = parsed.scheduled_at_utc.replace(tzinfo=None)
    from backend.app.schemas.gate2 import EventCreateIn

    event = create_event(
        db,
        user_id,
        EventCreateIn(
            title=parsed.reminder_title[:256],
            event_domain="reminder",
            event_type="user_reminder",
            starts_at=scheduled_naive,
            timezone=tz_name,
            source="chat",
            description="User-created reminder from chat",
            reminder_enabled=True,
        ),
    )

    dedupe_key = f"user_reminder:{user_id}:{event.get('id')}:{scheduled_naive.isoformat()}"
    payload = NotificationPayload(
        user_id=user_id,
        type="connection_ping",
        title="Reminder",
        body=parsed.reminder_title[:500],
        priority="normal",
        scheduled_for=scheduled_naive,
        dedupe_key=dedupe_key,
        category="reminder",
        source_type=NotificationSourceType.USER_EVENT.value,
        source_id=str(event.get("id")),
        template_key="user_chat_reminder",
        metadata={
            "language": "en",
            "conversation_id": conversation_id,
            "user_event_id": event.get("id"),
        },
    )
    from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily
    from backend.app.services.i10.self_producer_adapter import (
        build_self_occurrence_key,
        enqueue_self_scheduler_notification,
    )

    occurrence_key = build_self_occurrence_key(
        "user_chat_reminder",
        user_id=user_id,
        scheduled_for=scheduled_naive,
        extra=str(event.get("id")),
    )
    notification = enqueue_self_scheduler_notification(
        db,
        user_id=user_id,
        payload=payload,
        semantic_family=I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP,
        candidate_key=occurrence_key,
        source_type="user_chat_reminder",
        source_id=str(event.get("id")),
        privacy_class=I10PrivacyClass.PRIVATE,
    )
    return {
        "created": notification is not None,
        "user_event_id": event.get("id"),
        "notification_id": getattr(notification, "id", None),
        "scheduled_for": scheduled_naive.isoformat(),
        "timezone": tz_name,
    }
