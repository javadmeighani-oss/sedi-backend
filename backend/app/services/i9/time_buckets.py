"""Governed calendar bucket boundaries for I9 aggregation (reuse I7 period_bounds)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional, Tuple

from backend.app.services.i7.period_summaries import period_bounds, resolve_week_start

BucketKind = Literal["hourly", "daily", "weekly", "calendar_month", "yearly"]

_BUCKET_TO_SUMMARY = {
    "daily": "DAILY",
    "weekly": "WEEKLY",
    "calendar_month": "MONTHLY",
    "yearly": "YEARLY",
}


def bucket_bounds(
    bucket_kind: BucketKind,
    *,
    ref: datetime,
    preferred_language: Optional[str] = None,
) -> Tuple[datetime, datetime]:
    """Return UTC [start, end) for bucket containing ref. hourly uses UTC hour slice."""
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    if bucket_kind == "hourly":
        start = ref.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        from datetime import timedelta

        end = start + timedelta(hours=1)
        return start, end
    summary_type = _BUCKET_TO_SUMMARY[bucket_kind]
    week_start = resolve_week_start(preferred_language)
    return period_bounds(summary_type, now=ref, week_start=week_start)


def iter_bucket_starts(
    bucket_kind: BucketKind,
    *,
    range_start: datetime,
    range_end: datetime,
    preferred_language: Optional[str] = None,
) -> list[Tuple[datetime, datetime]]:
    """Enumerate bucket windows overlapping [range_start, range_end)."""
    if range_start.tzinfo is None:
        range_start = range_start.replace(tzinfo=timezone.utc)
    if range_end.tzinfo is None:
        range_end = range_end.replace(tzinfo=timezone.utc)
    buckets: list[Tuple[datetime, datetime]] = []
    cursor = range_start
    seen = set()
    while cursor < range_end:
        b_start, b_end = bucket_bounds(bucket_kind, ref=cursor, preferred_language=preferred_language)
        key = b_start.isoformat()
        if key not in seen:
            seen.add(key)
            if b_end > range_start and b_start < range_end:
                buckets.append((b_start, b_end))
        cursor = b_end
        if cursor <= b_start:
            break
    return buckets
