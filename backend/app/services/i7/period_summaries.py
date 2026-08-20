"""I7 period summaries — compression only, never higher authority than I6 facts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import PERM_READ, require_permission

SUMMARY_TZ = pytz.timezone("Asia/Tehran")
SUMMARY_TYPES = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
GENERATOR_VERSION = "i7-v1-lifelong-foundation"


class PeriodSummaryError(ValueError):
    pass


def resolve_week_start(preferred_language: Optional[str] = None) -> int:
    """0=Monday … 6=Sunday. fa-IR / fa default Saturday (5); else Monday."""
    lang = (preferred_language or "").strip().lower().replace("_", "-")
    if lang.startswith("fa"):
        return 5
    return 0


def period_bounds(
    summary_type: str,
    *,
    now: Optional[datetime] = None,
    week_start: int = 0,
    tz=None,
) -> tuple[datetime, datetime]:
    if summary_type not in SUMMARY_TYPES:
        raise PeriodSummaryError("INVALID_SUMMARY_TYPE")
    if week_start not in range(7):
        raise PeriodSummaryError("INVALID_WEEK_START")
    zone = tz or SUMMARY_TZ
    if now is None:
        aware = datetime.now(zone)
    elif now.tzinfo is None:
        aware = zone.localize(now) if hasattr(zone, "localize") else now.replace(tzinfo=zone)
    else:
        aware = now.astimezone(zone)
    start_local = aware.replace(hour=0, minute=0, second=0, microsecond=0)
    if summary_type == "DAILY":
        start = start_local
        end = start + timedelta(days=1)
    elif summary_type == "WEEKLY":
        delta = (start_local.weekday() - week_start) % 7
        start = start_local - timedelta(days=delta)
        end = start + timedelta(days=7)
    elif summary_type == "MONTHLY":
        start = start_local.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
    else:
        start = start_local.replace(month=1, day=1)
        end = start.replace(year=start.year + 1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def rebuild_summary(
    db: Session,
    user_id: int,
    summary_type: str = "DAILY",
    *,
    now: Optional[datetime] = None,
    commit: bool = True,
) -> models.UserPeriodSummary:
    """Wave-2: build from RAW/lower finalized summaries using user-local timezone."""
    from backend.app.services.i7.hierarchy import (
        build_daily_from_raw,
        build_higher_from_lower,
    )

    if summary_type == "DAILY":
        return build_daily_from_raw(db, user_id, now=now, finalize=True, commit=commit)
    if summary_type in ("WEEKLY", "MONTHLY", "YEARLY"):
        return build_higher_from_lower(
            db, user_id, summary_type, now=now, finalize=True, commit=commit
        )
    raise PeriodSummaryError("INVALID_SUMMARY_TYPE")


def invalidate_summaries_for_user(
    db: Session, user_id: int, *, reason: str, commit: bool = True
) -> int:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(models.UserPeriodSummary)
        .filter(models.UserPeriodSummary.user_id == user_id, models.UserPeriodSummary.status == "active")
        .all()
    )
    for row in rows:
        row.status = "stale"
        row.superseded_at = now
        row.narrative_summary = f"STALE:{reason}"
    if rows:
        if commit:
            db.commit()
        else:
            db.flush()
    return len(rows)
