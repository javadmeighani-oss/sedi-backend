"""User-local-day and TTL helpers for I8 operational plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from backend.app.services.gate4.policy_prefs_bridge import get_local_now, resolve_validated_user_timezone
from backend.app.services.i8.constants import CLEANUP_GRACE_HOURS


@dataclass(frozen=True)
class LocalDayWindow:
    user_local_date: date
    timezone_snapshot: str
    valid_from: datetime
    valid_until: datetime
    expires_at: datetime


def resolve_local_day_window(
    db: Session,
    user_id: int,
    *,
    now_utc: datetime | None = None,
) -> LocalDayWindow:
    tz_name = resolve_validated_user_timezone(db, user_id)
    now = now_utc or datetime.now(timezone.utc)
    local_now = get_local_now(now, tz_name)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1) - timedelta(microseconds=1)
    valid_from = start_local.astimezone(timezone.utc)
    valid_until = end_local.astimezone(timezone.utc)
    expires_at = valid_until + timedelta(hours=CLEANUP_GRACE_HOURS)
    return LocalDayWindow(
        user_local_date=start_local.date(),
        timezone_snapshot=tz_name,
        valid_from=valid_from,
        valid_until=valid_until,
        expires_at=expires_at,
    )
