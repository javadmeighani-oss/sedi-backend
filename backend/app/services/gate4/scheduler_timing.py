"""Gate 4D-5 — Scheduler daily notification timing (read-only; no sends/DB writes)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.models import NotificationPrefs, User, UserProfileCore
from backend.app.services.gate4.policy_prefs_bridge import (
    DEFAULT_DAILY_NOTIFICATION_TIME,
    DEFAULT_TIMEZONE,
    get_local_now,
    is_daily_notification_time,
    resolve_daily_notification_time,
    resolve_user_timezone,
)
from backend.app.services.memory import MemoryRepository

GATE4_DAILY_TOLERANCE_MINUTES = 10


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_memory_json_fact(db: Session, user_id: int, key: str) -> Optional[dict[str, Any]]:
    try:
        repo = MemoryRepository(db)
        fact = repo.get_fact(user_id=user_id, domain="preferences", key=key)
        if not fact or not fact.value_json:
            return None
        data = json.loads(fact.value_json)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _load_memory_morning_time(db: Session, user_id: int) -> Optional[Any]:
    data = _load_memory_json_fact(db, user_id, "morning_notification_time")
    if data is not None:
        return data
    return _load_memory_json_fact(db, user_id, "daily_notification_time")


def _load_memory_timezone(db: Session, user_id: int) -> Optional[Any]:
    data = _load_memory_json_fact(db, user_id, "timezone")
    if data is None:
        return None
    return data.get("tz") or data.get("timezone")


def resolve_user_daily_notification_time_for_scheduler(db: Session, user: User) -> str:
    """
    Resolve daily notification time for scheduler (HH:MM).

    Order: NotificationPrefs.daily_notification_time → memory fact → 08:00.
    """
    notification_prefs = (
        db.query(NotificationPrefs).filter(NotificationPrefs.user_id == user.id).first()
    )
    memory_time = _load_memory_morning_time(db, user.id)
    return resolve_daily_notification_time(
        notification_prefs=notification_prefs,
        memory_fact_time=memory_time,
    )


def resolve_user_timezone_for_scheduler(db: Session, user: User) -> str:
    """
    Resolve user timezone for scheduler.

    Order: UserProfileCore.timezone → memory fact → Asia/Tehran.
    """
    profile_core = (
        db.query(UserProfileCore).filter(UserProfileCore.user_id == user.id).first()
    )
    memory_tz = _load_memory_timezone(db, user.id)
    return resolve_user_timezone(
        profile_core=profile_core,
        memory_timezone=memory_tz,
    )


def should_run_daily_notification_gate4(
    db: Session,
    user: User,
    now_utc: datetime,
    *,
    tolerance_minutes: int = GATE4_DAILY_TOLERANCE_MINUTES,
) -> bool:
    """
    Return True when local time is within the daily notification tolerance window.

    Read-only — does not write DB or create notifications.
    """
    daily_time = resolve_user_daily_notification_time_for_scheduler(db, user)
    tz_name = resolve_user_timezone_for_scheduler(db, user)
    local_dt = get_local_now(_ensure_utc(now_utc), tz_name)
    return is_daily_notification_time(
        local_dt,
        daily_time,
        tolerance_minutes=tolerance_minutes,
    )


def legacy_should_run_morning_notification(
    memory_repo: MemoryRepository,
    user: User,
    now_utc: datetime,
    *,
    morning_hour_default: int = 9,
    tolerance_minutes: int = GATE4_DAILY_TOLERANCE_MINUTES,
) -> bool:
    """
    Legacy scheduler timing check (MORNING_HOUR=9 default, memory facts).

    Preserves pre-Gate-4D-5 behavior for use when SEDI_GATE4_DAILY_0800_ENABLED is false.
    """
    import pytz

    morning_time_fact = memory_repo.get_fact(
        user_id=user.id,
        domain="preferences",
        key="morning_notification_time",
    )

    morning_hour = morning_hour_default
    morning_minute = 0

    if morning_time_fact:
        try:
            time_data = json.loads(morning_time_fact.value_json)
            morning_hour = time_data.get("hour", morning_hour_default)
            morning_minute = time_data.get("minute", 0)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    from backend.app.models import UserProfileCore

    profile_core = (
        memory_repo.db.query(UserProfileCore).filter(UserProfileCore.user_id == user.id).first()
        if getattr(memory_repo, "db", None) is not None
        else None
    )
    tz_str = DEFAULT_TIMEZONE
    if profile_core and profile_core.timezone:
        tz_str = str(profile_core.timezone).strip() or DEFAULT_TIMEZONE
    else:
        timezone_fact = memory_repo.get_fact(
            user_id=user.id,
            domain="preferences",
            key="timezone",
        )
        if timezone_fact:
            try:
                tz_data = json.loads(timezone_fact.value_json)
                tz_str = tz_data.get("tz", DEFAULT_TIMEZONE) if isinstance(tz_data, dict) else str(tz_data)
            except (json.JSONDecodeError, TypeError):
                pass
    try:
        user_tz = pytz.timezone(tz_str)
    except pytz.exceptions.UnknownTimeZoneError:
        user_tz = pytz.timezone(DEFAULT_TIMEZONE)

    now = _ensure_utc(now_utc)
    if now.tzinfo is None:
        now_local = now.replace(tzinfo=timezone.utc).astimezone(user_tz)
    else:
        now_local = now.astimezone(user_tz)

    current_hour = now_local.hour
    current_minute = now_local.minute

    if current_hour != morning_hour:
        return False
    if current_minute < morning_minute or current_minute >= morning_minute + tolerance_minutes:
        return False
    return True
