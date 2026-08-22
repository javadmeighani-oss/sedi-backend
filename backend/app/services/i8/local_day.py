"""User-local-day and TTL helpers for I8 operational plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from backend.app.models import UserProfileCore
from backend.app.services.i8.constants import CLEANUP_GRACE_HOURS


class I8TimezoneRequiredError(Exception):
    """UserProfileCore.timezone is missing or empty."""


class I8InvalidTimezoneError(Exception):
    """UserProfileCore.timezone is not a valid IANA identifier."""


@dataclass(frozen=True)
class LocalDayWindow:
    user_local_date: date
    timezone_snapshot: str
    valid_from: datetime
    valid_until: datetime
    expires_at: datetime


def resolve_i8_strict_timezone(db: Session, user_id: int) -> str:
    """I8-only timezone authority: UserProfileCore.timezone, no fallbacks."""
    profile = db.query(UserProfileCore).filter(UserProfileCore.user_id == user_id).first()
    if profile is None or not profile.timezone or not str(profile.timezone).strip():
        raise I8TimezoneRequiredError("UserProfileCore.timezone is required for I8 operational plans.")
    tz_name = str(profile.timezone).strip()
    try:
        pytz.timezone(tz_name)
    except pytz.exceptions.UnknownTimeZoneError as exc:
        raise I8InvalidTimezoneError(f"Invalid IANA timezone: {tz_name}") from exc
    return tz_name


def _local_now_from_utc(now_utc: datetime, tz_name: str) -> datetime:
    aware = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc)
    return aware.astimezone(pytz.timezone(tz_name))


def resolve_local_day_window(
    db: Session,
    user_id: int,
    *,
    now_utc: datetime | None = None,
) -> LocalDayWindow:
    tz_name = resolve_i8_strict_timezone(db, user_id)
    now = now_utc or datetime.now(timezone.utc)
    local_now = _local_now_from_utc(now, tz_name)
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
