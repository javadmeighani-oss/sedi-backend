"""
Gate 4D — Policy prefs bridge (read-only).

Resolves quiet hours, daily time, and timezone from NotificationPrefs with safe
memory-fact fallback. No writes, FCM, or scheduler sends.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytz
from sqlalchemy.orm import Session

from backend.app.models import NotificationPrefs, User, UserProfileCore
from backend.app.services.gate4.notification_contract import DEFAULT_DAILY_NOTIFICATION_TIME
from backend.app.services.memory import MemoryRepository

DEFAULT_TIMEZONE = "Asia/Tehran"
HHMM_REGEX = re.compile(r"^\d{2}:\d{2}$")


def validate_hhmm_24h(value: str, *, field_name: str = "time") -> str:
    """Validate strict 24-hour HH:MM."""
    text = (value or "").strip()
    if not HHMM_REGEX.match(text):
        raise ValueError(f"{field_name} must be HH:MM")
    hour, minute = map(int, text.split(":"))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"{field_name} must be a valid 24-hour time")
    return text


def resolve_daily_notification_time(
    *,
    notification_prefs: Any = None,
    memory_fact_time: Any = None,
) -> str:
    """
    Resolve daily notification time (HH:MM).

    Order: prefs.daily_notification_time → memory {hour, minute} → 08:00.
    """
    prefs_time = getattr(notification_prefs, "daily_notification_time", None) if notification_prefs else None
    if prefs_time:
        try:
            return validate_hhmm_24h(str(prefs_time), field_name="daily_notification_time")
        except ValueError:
            pass

    if isinstance(memory_fact_time, dict):
        hour = memory_fact_time.get("hour")
        minute = memory_fact_time.get("minute", 0)
        if hour is not None:
            try:
                return validate_hhmm_24h(f"{int(hour):02d}:{int(minute):02d}")
            except ValueError:
                pass
    elif isinstance(memory_fact_time, str) and memory_fact_time.strip():
        try:
            return validate_hhmm_24h(memory_fact_time.strip())
        except ValueError:
            pass

    return DEFAULT_DAILY_NOTIFICATION_TIME


def resolve_validated_user_timezone(
    db: Session,
    user_id: int,
) -> str:
    """
    Resolve IANA timezone for a user (profile → memory → default).

    Invalid IANA values fall back to ``DEFAULT_TIMEZONE`` (same policy as scheduler/quiet hours).
    """
    from sqlalchemy import inspect as sa_inspect

    profile_core = None
    bind = db.get_bind()
    try:
        if sa_inspect(bind).has_table("user_profile_core"):
            profile_core = (
                db.query(UserProfileCore).filter(UserProfileCore.user_id == user_id).first()
            )
    except Exception:
        profile_core = None
    user = db.query(User).filter(User.id == user_id).first()
    memory_tz = None
    try:
        if sa_inspect(bind).has_table("user_memory_facts"):
            memory_tz = _load_memory_json_fact(db, user_id, "timezone")
    except Exception:
        memory_tz = None
    tz_candidate = resolve_user_timezone(
        user=user,
        profile_core=profile_core,
        memory_timezone=memory_tz,
    )
    try:
        pytz.timezone(tz_candidate)
        return tz_candidate
    except pytz.exceptions.UnknownTimeZoneError:
        return DEFAULT_TIMEZONE


def resolve_user_timezone(
    *,
    user: User | None = None,
    profile_core: UserProfileCore | None = None,
    memory_timezone: Any = None,
) -> str:
    """Resolve timezone: profile → user hint → memory → default."""
    if profile_core and profile_core.timezone:
        tz = str(profile_core.timezone).strip()
        if tz:
            return tz
    if memory_timezone:
        if isinstance(memory_timezone, dict):
            candidate = memory_timezone.get("tz") or memory_timezone.get("timezone")
        else:
            candidate = str(memory_timezone)
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    return DEFAULT_TIMEZONE


def get_local_now(now_utc: datetime, tz_name: str) -> datetime:
    """Convert UTC now to user-local aware datetime."""
    aware = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
    try:
        user_tz = pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError:
        user_tz = pytz.timezone(DEFAULT_TIMEZONE)
    return aware.astimezone(user_tz)


def _minutes_in_day(hour: int, minute: int) -> int:
    return hour * 60 + minute


def is_within_quiet_window_local(
    *,
    local_now: datetime,
    quiet_start: str,
    quiet_end: str,
) -> bool:
    """Return True when local time is inside quiet window."""
    try:
        sh, sm = map(int, quiet_start.split(":"))
        eh, em = map(int, quiet_end.split(":"))
    except (ValueError, AttributeError):
        return False
    now_minutes = local_now.hour * 60 + local_now.minute
    start_minutes = _minutes_in_day(sh, sm)
    end_minutes = _minutes_in_day(eh, em)
    if start_minutes > end_minutes:
        return now_minutes >= start_minutes or now_minutes < end_minutes
    return start_minutes <= now_minutes < end_minutes


def is_daily_notification_time(
    local_dt: datetime,
    daily_time: str,
    *,
    tolerance_minutes: int = 10,
) -> bool:
    """True when local_dt is within tolerance window of daily_time."""
    try:
        daily_time = validate_hhmm_24h(daily_time)
        hour, minute = map(int, daily_time.split(":"))
    except ValueError:
        return False
    target = local_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = abs((local_dt - target).total_seconds()) / 60.0
    return delta < max(tolerance_minutes, 1)


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


@dataclass(frozen=True)
class UserQuietHoursSnapshot:
    enabled: bool
    quiet_start: Optional[str]
    quiet_end: Optional[str]
    timezone: str
    is_quiet_now: bool
    local_time: str


def load_quiet_hours_snapshot(
    db: Session,
    *,
    user_id: int,
    now_utc: datetime | None = None,
) -> UserQuietHoursSnapshot:
    """
    Load quiet-hours snapshot: NotificationPrefs first, memory fallback.

    Fail-open: disabled when prefs/memory missing or invalid.
    """
    effective_now = now_utc or datetime.now(timezone.utc)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=timezone.utc)

    notification_prefs = (
        db.query(NotificationPrefs).filter(NotificationPrefs.user_id == user_id).first()
    )
    profile_core = (
        db.query(UserProfileCore).filter(UserProfileCore.user_id == user_id).first()
    )
    user = db.query(User).filter(User.id == user_id).first()
    memory_tz = _load_memory_json_fact(db, user_id, "timezone")
    tz_name = resolve_user_timezone(
        user=user,
        profile_core=profile_core,
        memory_timezone=memory_tz,
    )
    local_now = get_local_now(effective_now, tz_name)
    local_time = f"{local_now.hour:02d}:{local_now.minute:02d}"

    enabled = False
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None

    if notification_prefs is not None:
        quiet_start = notification_prefs.quiet_start
        quiet_end = notification_prefs.quiet_end
        if notification_prefs.quiet_hours_enabled and quiet_start and quiet_end:
            enabled = True
        elif not notification_prefs.quiet_hours_enabled:
            enabled = False

    if not enabled:
        memory_qh = _load_memory_json_fact(db, user_id, "quiet_hours")
        if memory_qh and memory_qh.get("enabled"):
            quiet_start = str(memory_qh.get("start") or "22:00")
            quiet_end = str(memory_qh.get("end") or "08:00")
            enabled = True

    is_quiet = False
    if enabled and quiet_start and quiet_end:
        is_quiet = is_within_quiet_window_local(
            local_now=local_now,
            quiet_start=quiet_start,
            quiet_end=quiet_end,
        )

    return UserQuietHoursSnapshot(
        enabled=enabled,
        quiet_start=quiet_start,
        quiet_end=quiet_end,
        timezone=tz_name,
        is_quiet_now=is_quiet,
        local_time=local_time,
    )


@dataclass(frozen=True)
class UserNotificationPolicyPrefs:
    """Read-only prefs snapshot for policy evaluation."""

    quiet_hours_enabled: bool
    quiet_start: Optional[str]
    quiet_end: Optional[str]
    is_quiet_hours_now: bool
    local_time: str
    user_timezone: str
    daily_notification_time: str
    user_channel_enabled: bool = True
    user_category_enabled: bool = True
    feedback_suppressed: bool = False


def load_user_notification_policy_prefs(
    db: Session,
    user_id: int,
    *,
    now_utc: datetime | None = None,
    channel: str = "push",
) -> UserNotificationPolicyPrefs:
    """Load resolved prefs snapshot for policy evaluation (read-only)."""
    effective_now = now_utc or datetime.now(timezone.utc)
    quiet = load_quiet_hours_snapshot(db, user_id=user_id, now_utc=effective_now)
    notification_prefs = (
        db.query(NotificationPrefs).filter(NotificationPrefs.user_id == user_id).first()
    )
    memory_daily = _load_memory_json_fact(db, user_id, "morning_notification_time")
    if memory_daily is None:
        memory_daily = _load_memory_json_fact(db, user_id, "daily_notification_time")

    daily_time = resolve_daily_notification_time(
        notification_prefs=notification_prefs,
        memory_fact_time=memory_daily,
    )

    channel_enabled = True
    category_enabled = True
    if notification_prefs is not None:
        ch = (channel or "push").strip().lower()
        if ch in ("companion", "engagement"):
            channel_enabled = notification_prefs.companion_enabled
        elif ch in ("health_alert", "health"):
            channel_enabled = notification_prefs.health_alert_enabled
        elif ch in ("medication", "medication_reminder", "reminder_medication"):
            channel_enabled = notification_prefs.reminder_medication_enabled
        elif ch in ("appointment", "reminder_appointment"):
            channel_enabled = notification_prefs.reminder_appointment_enabled
        elif ch in ("system", "reminder_system"):
            channel_enabled = notification_prefs.reminder_system_enabled

    return UserNotificationPolicyPrefs(
        quiet_hours_enabled=quiet.enabled,
        quiet_start=quiet.quiet_start,
        quiet_end=quiet.quiet_end,
        is_quiet_hours_now=quiet.is_quiet_now,
        local_time=quiet.local_time,
        user_timezone=quiet.timezone,
        daily_notification_time=daily_time,
        user_channel_enabled=channel_enabled,
        user_category_enabled=category_enabled,
        feedback_suppressed=False,
    )
