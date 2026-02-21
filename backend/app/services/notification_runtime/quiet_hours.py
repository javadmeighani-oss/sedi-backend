# backend.app.services.notification_runtime.quiet_hours
"""
Quiet hours suppression (Stage 16.6.4).

Uses UserMemoryFact key "quiet_hours" (JSON: {start, end, enabled})
and "timezone" (JSON: {tz}) for user-local time.
"""

import json
from datetime import datetime
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from backend.app.services.memory import MemoryRepository


def is_within_quiet_window(db: Session, user_id: int) -> bool:
    """
    Return True if current time (user local) is within the configured quiet window.
    No channel/priority logic; use this when you need the raw "in window" signal
    (e.g. D2 guard so logs and reason correctly reflect quiet window).
    """
    repo = MemoryRepository(db)
    qh_fact = repo.get_fact(user_id=user_id, domain="preferences", key="quiet_hours")
    if not qh_fact or not qh_fact.value_json:
        return False
    try:
        data = json.loads(qh_fact.value_json)
        if not isinstance(data, dict) or not data.get("enabled", False):
            return False
        start_str = data.get("start", "22:00")
        end_str = data.get("end", "08:00")
    except (json.JSONDecodeError, TypeError, KeyError):
        return False

    try:
        sh, sm = map(int, str(start_str).split(":")[:2])
        eh, em = map(int, str(end_str).split(":")[:2])
    except (ValueError, IndexError):
        return False

    tz_str = "Asia/Tehran"
    tz_fact = repo.get_fact(user_id=user_id, domain="preferences", key="timezone")
    if tz_fact and tz_fact.value_json:
        try:
            tz_data = json.loads(tz_fact.value_json)
            tz_str = tz_data.get("tz", tz_str) if isinstance(tz_data, dict) else str(tz_data)
        except (json.JSONDecodeError, TypeError):
            pass
    try:
        user_tz = pytz.timezone(tz_str)
    except pytz.exceptions.UnknownTimeZoneError:
        user_tz = pytz.timezone("Asia/Tehran")

    now_local = datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(user_tz)
    now_minutes = now_local.hour * 60 + now_local.minute
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em

    if start_minutes > end_minutes:
        within = now_minutes >= start_minutes or now_minutes < end_minutes
    else:
        within = start_minutes <= now_minutes < end_minutes
    return within


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
    - Uses UserMemoryFact "quiet_hours" and "timezone"
    """
    repo = MemoryRepository(db)
    qh_fact = repo.get_fact(user_id=user_id, domain="preferences", key="quiet_hours")
    if not qh_fact or not qh_fact.value_json:
        return False
    try:
        data = json.loads(qh_fact.value_json)
        if not isinstance(data, dict) or not data.get("enabled", False):
            return False
        start_str = data.get("start", "22:00")
        end_str = data.get("end", "08:00")
    except (json.JSONDecodeError, TypeError, KeyError):
        return False

    # Parse HH:MM
    try:
        sh, sm = map(int, str(start_str).split(":")[:2])
        eh, em = map(int, str(end_str).split(":")[:2])
    except (ValueError, IndexError):
        return False

    # Resolve user timezone
    tz_str = "Asia/Tehran"
    tz_fact = repo.get_fact(user_id=user_id, domain="preferences", key="timezone")
    if tz_fact and tz_fact.value_json:
        try:
            tz_data = json.loads(tz_fact.value_json)
            tz_str = tz_data.get("tz", tz_str) if isinstance(tz_data, dict) else str(tz_data)
        except (json.JSONDecodeError, TypeError):
            pass
    try:
        user_tz = pytz.timezone(tz_str)
    except pytz.exceptions.UnknownTimeZoneError:
        user_tz = pytz.timezone("Asia/Tehran")

    now_local = datetime.utcnow().replace(tzinfo=pytz.UTC).astimezone(user_tz)
    now_minutes = now_local.hour * 60 + now_local.minute
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em

    # Overnight range (e.g. 22:00–08:00): in range if >= start OR < end
    if start_minutes > end_minutes:
        within = now_minutes >= start_minutes or now_minutes < end_minutes
    else:
        within = start_minutes <= now_minutes < end_minutes

    if not within:
        return False

    # Within quiet hours: check channel/priority
    if channel in ("morning", "engagement"):
        return True
    if channel == "health_alert":
        return priority != "critical"
    return False
