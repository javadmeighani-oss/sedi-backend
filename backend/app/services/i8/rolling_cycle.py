"""Rolling 7-local-day cycle discovery from I8-owned presentation metadata.

cycle_start_local_date in action presentation_json is the schema-free anchor.
No ISO week authority. No separate weekly store.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from backend.app.services.i8.local_day import (
    CYCLE_START_META_KEY,
    WEEKLY_CYCLE_DAYS,
    WeeklyCycleBounds,
    bounds_for_cycle_start,
    local_today_for_user,
    parse_cycle_start_meta,
    rolling_cycle_end,
)
from backend.app.services.i8.repository import I8OperationalRepository

_REPO = I8OperationalRepository()

# Bound scan window so we do not invent cycles from unbounded history.
_CYCLE_LOOKBACK_DAYS = 28


def _presentation_cycle_start(presentation_json: str | None) -> date | None:
    if not presentation_json:
        return None
    try:
        parsed = json.loads(presentation_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parse_cycle_start_meta(parsed.get(CYCLE_START_META_KEY))


def discover_stamped_cycle_starts(
    db: Session,
    user_id: int,
    *,
    today_local: date,
) -> list[date]:
    """Deterministic cycle anchors from I8 presentation metadata only."""
    since = today_local - timedelta(days=_CYCLE_LOOKBACK_DAYS)
    plans = _REPO.list_plans_for_date_range(
        db,
        user_id=int(user_id),
        start_date=since,
        end_date=today_local + timedelta(days=WEEKLY_CYCLE_DAYS),
        statuses=("ACTIVE", "COMPLETED", "SUPERSEDED"),
    )
    actions = _REPO.list_actions_for_plans(
        db, user_id=int(user_id), plan_ids=[int(p.id) for p in plans]
    )
    starts: set[date] = set()
    for action in actions:
        stamped = _presentation_cycle_start(action.presentation_json)
        if stamped is not None:
            starts.add(stamped)
    return sorted(starts, reverse=True)


def find_active_cycle_start(cycle_starts: Iterable[date], today_local: date) -> date | None:
    for start in sorted(set(cycle_starts), reverse=True):
        end = rolling_cycle_end(start)
        if start <= today_local <= end:
            return start
    return None


def select_projection_cycle(
    cycle_starts: list[date],
    today_local: date,
) -> tuple[str, Optional[date]]:
    """
    Returns (state, cycle_start).
    active: today inside a stamped cycle (newest wins)
    review_due: newest stamped cycle has ended; no newer active
    empty: no stamped cycles
    """
    if not cycle_starts:
        return "empty", None
    active = find_active_cycle_start(cycle_starts, today_local)
    if active is not None:
        return "active", active
    newest = max(cycle_starts)
    if today_local > rolling_cycle_end(newest):
        return "review_due", newest
    return "empty", None


def resolve_persist_cycle_bounds(
    db: Session,
    user_id: int,
    *,
    now_utc: datetime | None = None,
    target_local_date: date | None = None,
) -> WeeklyCycleBounds:
    """
    Resolve rolling cycle for persist:
    - reuse active stamped cycle when today is inside it
    - otherwise start a new cycle at target_local_date or today
    """
    tz_name, today_local = local_today_for_user(db, user_id, now_utc=now_utc)
    starts = discover_stamped_cycle_starts(db, user_id, today_local=today_local)
    active = find_active_cycle_start(starts, today_local)
    if active is not None:
        cycle_start = active
        is_new = False
    else:
        cycle_start = target_local_date if target_local_date is not None else today_local
        is_new = True
    effective_target = target_local_date if target_local_date is not None else today_local
    return bounds_for_cycle_start(
        cycle_start=cycle_start,
        timezone_snapshot=tz_name,
        today_local=today_local,
        target_local_date=effective_target,
        is_new_cycle=is_new,
    )
