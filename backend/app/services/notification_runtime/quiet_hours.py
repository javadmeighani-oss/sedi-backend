# backend.app.services.notification_runtime.quiet_hours
"""
Quiet hours suppression (Stage 16.6.4).

Canonical owner: NotificationPrefs (then UserProfileCore quiet window).
Governed I6 preferences.quiet_hours is compatibility-only.
Timezone owner: UserProfileCore (I6 preferences.timezone is compatibility-only).
"""

import json
from datetime import datetime
from typing import Optional, Tuple

import pytz
from sqlalchemy.orm import Session

from backend.app.models import NotificationPrefs, UserProfileCore
from backend.app.services.gate4.policy_prefs_bridge import DEFAULT_TIMEZONE, resolve_validated_user_timezone
from backend.app.services.i6.memory_writes import get_readable_fact_or_none


def _hhmm(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    hour = getattr(value, "hour", None)
    minute = getattr(value, "minute", None)
    if hour is None or minute is None:
        return None
    return f"{int(hour):02d}:{int(minute):02d}"


def _canonical_quiet_window(db: Session, user_id: int) -> Optional[Tuple[str, str]]:
    prefs = db.query(NotificationPrefs).filter(NotificationPrefs.user_id == user_id).first()
    if prefs is not None and prefs.quiet_hours_enabled:
        start = _hhmm(prefs.quiet_start)
        end = _hhmm(prefs.quiet_end)
        if start and end:
            return start, end
    core = db.query(UserProfileCore).filter(UserProfileCore.user_id == user_id).first()
    if core is not None:
        start = _hhmm(core.quiet_start)
        end = _hhmm(core.quiet_end)
        if start and end:
            return start, end
    qh_fact = get_readable_fact_or_none(db, user_id, "preferences", "quiet_hours")
    if qh_fact and qh_fact.value_json:
        try:
            data = json.loads(qh_fact.value_json)
            if isinstance(data, dict) and data.get("enabled", False):
                start = data.get("start")
                end = data.get("end")
                if start and end:
                    return str(start), str(end)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None
    return None


def is_within_quiet_window(db: Session, user_id: int) -> bool:
    """
    Return True if current time (user local) is within the configured quiet window.
    No channel/priority logic; use this when you need the raw "in window" signal
    (e.g. D2 guard so logs and reason correctly reflect quiet window).
    """
    window = _canonical_quiet_window(db, user_id)
    if window is None:
        return False
    start_str, end_str = window
    try:
        sh, sm = map(int, str(start_str).split(":")[:2])
        eh, em = map(int, str(end_str).split(":")[:2])
    except (ValueError, IndexError):
        return False

    tz_str = resolve_validated_user_timezone(db, user_id)
    try:
        user_tz = pytz.timezone(tz_str)
    except pytz.exceptions.UnknownTimeZoneError:
        user_tz = pytz.timezone(DEFAULT_TIMEZONE)

    now_local = datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(user_tz)
    now_minutes = now_local.hour * 60 + now_local.minute
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em

    if start_minutes > end_minutes:
        return now_minutes >= start_minutes or now_minutes < end_minutes
    return start_minutes <= now_minutes < end_minutes


def is_within_quiet_hours(
    db: Session,
    user_id: int,
    channel: str,
    priority: str,
) -> bool:
    """
    Return True if we should suppress this notification due to quiet hours.

    - morning, engagement: suppress if within quiet hours
    - health_alert: suppress only if priority != "critical"
    """
    if not is_within_quiet_window(db, user_id):
        return False
    if channel in ("morning", "engagement"):
        return True
    if channel == "health_alert":
        return priority != "critical"
    return False
