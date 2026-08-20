"""I7 raw retention eligibility — fail-closed after retain_until."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import or_

from backend.app import models

RAW_VISIBLE_DAYS = 30


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def is_raw_visible(row: models.Memory, *, now: Optional[datetime] = None) -> bool:
    """Expired raw is invisible even before physical purge."""
    when = now or utcnow()
    retain = as_utc(getattr(row, "retain_until", None))
    if retain is None:
        # Legacy unset: fail-closed for product visibility (Wave-2).
        return False
    return retain > when


def eligible_raw_filter(query: Query, *, now: Optional[datetime] = None) -> Query:
    when = now or utcnow()
    return query.filter(
        models.Memory.durable_write.is_(True),
        models.Memory.retain_until.isnot(None),
        models.Memory.retain_until > when,
    )


def query_eligible_raw(
    db: Session,
    user_id: int,
    *,
    now: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> list[models.Memory]:
    q = (
        eligible_raw_filter(db.query(models.Memory), now=now)
        .filter(models.Memory.user_id == user_id)
        .order_by(models.Memory.created_at.desc())
    )
    if limit is not None:
        q = q.limit(limit)
    return list(q.all())


def query_eligible_raw_for_local_day(
    db: Session,
    user_id: int,
    local_period_date,
    *,
    now: Optional[datetime] = None,
) -> list[models.Memory]:
    q = (
        eligible_raw_filter(db.query(models.Memory), now=now)
        .filter(
            models.Memory.user_id == user_id,
            models.Memory.local_period_date == local_period_date,
        )
        .order_by(models.Memory.created_at.asc())
    )
    return list(q.all())
