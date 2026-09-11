"""User-local-day and rolling 7-day cycle helpers for I8 operational plans."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import pytz
from sqlalchemy.orm import Session

from backend.app.models import UserProfileCore
from backend.app.services.i8.constants import CLEANUP_GRACE_HOURS

# Bounded Lifestyle weekly cycle length (local dates). Not a calendar engine.
WEEKLY_CYCLE_DAYS = 7
# I8-owned presentation metadata key (schema-free cycle anchor).
CYCLE_START_META_KEY = "cycle_start_local_date"


class I8TimezoneRequiredError(Exception):
    """UserProfileCore.timezone is missing or empty."""


class I8InvalidTimezoneError(Exception):
    """UserProfileCore.timezone is not a valid IANA identifier."""


class I8TargetDateOutOfCycleError(Exception):
    """target_local_date is outside the bounded current 7-day cycle."""


@dataclass(frozen=True)
class LocalDayWindow:
    user_local_date: date
    timezone_snapshot: str
    valid_from: datetime
    valid_until: datetime
    expires_at: datetime


@dataclass(frozen=True)
class WeeklyCycleBounds:
    cycle_start: date
    cycle_end: date
    timezone_snapshot: str
    today_local: date
    day_index: int | None = None  # 1..7 when a target date is in-cycle
    is_new_cycle: bool = False


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


def _local_midnight(tz: pytz.BaseTzInfo, local_date: date) -> datetime:
    """DST-safe local calendar midnight via independent localization."""
    return tz.localize(datetime.combine(local_date, time.min), is_dst=None)


def local_day_utc_span_seconds(window: LocalDayWindow) -> float:
    """Seconds from valid_from through end of local day (exclusive next midnight)."""
    next_midnight = window.valid_until + timedelta(microseconds=1)
    return (next_midnight - window.valid_from).total_seconds()


def _window_for_local_date(tz_name: str, local_date: date) -> LocalDayWindow:
    tz = pytz.timezone(tz_name)
    start_local = _local_midnight(tz, local_date)
    next_start_local = _local_midnight(tz, local_date + timedelta(days=1))
    valid_from = start_local.astimezone(timezone.utc)
    next_day_start_utc = next_start_local.astimezone(timezone.utc)
    valid_until = next_day_start_utc - timedelta(microseconds=1)
    expires_at = valid_until + timedelta(hours=CLEANUP_GRACE_HOURS)
    return LocalDayWindow(
        user_local_date=local_date,
        timezone_snapshot=tz_name,
        valid_from=valid_from,
        valid_until=valid_until,
        expires_at=expires_at,
    )


def resolve_local_day_window(
    db: Session,
    user_id: int,
    *,
    now_utc: datetime | None = None,
) -> LocalDayWindow:
    tz_name = resolve_i8_strict_timezone(db, user_id)
    now = now_utc or datetime.now(timezone.utc)
    local_date = _local_now_from_utc(now, tz_name).date()
    return _window_for_local_date(tz_name, local_date)


def local_today_for_user(
    db: Session,
    user_id: int,
    *,
    now_utc: datetime | None = None,
) -> tuple[str, date]:
    """Return (timezone_name, today_local) with strict TZ authority."""
    tz_name = resolve_i8_strict_timezone(db, user_id)
    now = now_utc or datetime.now(timezone.utc)
    return tz_name, _local_now_from_utc(now, tz_name).date()


def rolling_cycle_end(cycle_start: date) -> date:
    """cycle_end = cycle_start + 6 local calendar days (exactly 7 dates)."""
    return cycle_start + timedelta(days=WEEKLY_CYCLE_DAYS - 1)


def parse_cycle_start_meta(raw: object) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    text = str(raw).strip()[:32]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def day_index_for(cycle_start: date, local_date: date) -> int:
    return (local_date - cycle_start).days + 1


def bounds_for_cycle_start(
    *,
    cycle_start: date,
    timezone_snapshot: str,
    today_local: date,
    target_local_date: date | None = None,
    is_new_cycle: bool = False,
) -> WeeklyCycleBounds:
    cycle_end = rolling_cycle_end(cycle_start)
    day_index = None
    if target_local_date is not None:
        if target_local_date < cycle_start or target_local_date > cycle_end:
            raise I8TargetDateOutOfCycleError(
                f"target_local_date {target_local_date.isoformat()} outside "
                f"{cycle_start.isoformat()}..{cycle_end.isoformat()}"
            )
        day_index = day_index_for(cycle_start, target_local_date)
    return WeeklyCycleBounds(
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        timezone_snapshot=timezone_snapshot,
        today_local=today_local,
        day_index=day_index,
        is_new_cycle=is_new_cycle,
    )


def resolve_local_day_window_for_date(
    db: Session,
    user_id: int,
    target_local_date: date,
    *,
    now_utc: datetime | None = None,
) -> LocalDayWindow:
    """DST-safe window for an explicit local date (timezone fail-closed)."""
    tz_name = resolve_i8_strict_timezone(db, user_id)
    # Touch now_utc for API symmetry / future clock injection.
    _ = now_utc or datetime.now(timezone.utc)
    return _window_for_local_date(tz_name, target_local_date)
