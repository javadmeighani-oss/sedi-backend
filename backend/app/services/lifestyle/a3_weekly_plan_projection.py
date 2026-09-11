"""A3 Lifestyle weekly nutrition/exercise projection — read-only I8 aggregation.

Rolling 7 local-day cycles anchored by I8 presentation cycle_start_local_date.
No plan generation. No fake placeholders. No ISO-week authority.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.app.services.i8.local_day import (
    CYCLE_START_META_KEY,
    WEEKLY_CYCLE_DAYS,
    I8InvalidTimezoneError,
    I8TimezoneRequiredError,
    local_today_for_user,
    rolling_cycle_end,
)
from backend.app.services.i8.repository import I8OperationalRepository
from backend.app.services.i8.rolling_cycle import (
    discover_stamped_cycle_starts,
    select_projection_cycle,
)

_REPO = I8OperationalRepository()

_ACTION_STATUSES = frozenset({"ACTIVE", "COMPLETED"})


def _safe_presentation(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _compact_action(action) -> dict[str, Any]:
    pres = _safe_presentation(action.presentation_json)
    item: dict[str, Any] = {
        "title": (action.summary_text or action.action_type or "Action")[:256],
        "status": (action.status or "ACTIVE")[:32],
        "action_type": (action.action_type or "")[:64],
    }
    for key in (
        "local_date",
        "local_time",
        "day_index",
        "meal_slot",
        "activity_type",
        "activity_title",
        "duration_minutes",
        "title",
        CYCLE_START_META_KEY,
    ):
        if key in pres and pres[key] is not None and pres[key] != "":
            item[key] = pres[key]
    if not item.get("title") and pres.get("activity_title"):
        item["title"] = str(pres["activity_title"])[:256]
    return item


def build_lifestyle_weekly_plan_projection(
    db: Session,
    user_id: int,
    *,
    now_utc=None,
) -> dict[str, Any]:
    """
    Exactly 7 local dates when a stamped cycle exists. Side-effect free.

    review_due: most recent stamped cycle ended and no newer active cycle.
    Does NOT auto-create next cycle.
    """
    try:
        tz_name, today_local = local_today_for_user(
            db, int(user_id), now_utc=now_utc
        )
    except (I8TimezoneRequiredError, I8InvalidTimezoneError):
        return {
            "cycle_start": None,
            "cycle_end": None,
            "timezone": None,
            "state": "unavailable",
            "review_due": False,
            "days": [],
        }

    starts = discover_stamped_cycle_starts(
        db, int(user_id), today_local=today_local
    )
    state, cycle_start = select_projection_cycle(starts, today_local)
    review_due = state == "review_due"

    if state == "empty" or cycle_start is None:
        return {
            "cycle_start": None,
            "cycle_end": None,
            "timezone": tz_name,
            "state": "empty",
            "review_due": False,
            "days": [],
        }

    cycle_end = rolling_cycle_end(cycle_start)
    plans = _REPO.list_plans_for_date_range(
        db,
        user_id=int(user_id),
        start_date=cycle_start,
        end_date=cycle_end,
    )

    # Prefer ACTIVE plan per local_date; else first COMPLETED (shared daily header).
    plan_by_date: dict[date, Any] = {}
    for p in plans:
        d = p.user_local_date
        existing = plan_by_date.get(d)
        if existing is None:
            plan_by_date[d] = p
        elif existing.status != "ACTIVE" and p.status == "ACTIVE":
            plan_by_date[d] = p

    selected = list(plan_by_date.values())
    actions = _REPO.list_actions_for_plans(
        db, user_id=int(user_id), plan_ids=[int(p.id) for p in selected]
    )
    actions_by_plan: dict[int, list] = {}
    for a in actions:
        if (a.status or "").upper() not in _ACTION_STATUSES:
            continue
        # Only include actions belonging to this cycle anchor.
        stamped = _safe_presentation(a.presentation_json).get(CYCLE_START_META_KEY)
        if stamped and str(stamped) != cycle_start.isoformat():
            continue
        actions_by_plan.setdefault(int(a.plan_id), []).append(a)

    days: list[dict[str, Any]] = []
    for i in range(WEEKLY_CYCLE_DAYS):
        local_d = cycle_start + timedelta(days=i)
        plan = plan_by_date.get(local_d)
        nutrition: list[dict[str, Any]] = []
        exercise: list[dict[str, Any]] = []
        if plan is not None:
            for a in actions_by_plan.get(int(plan.id), []):
                domain = (a.action_domain or "").lower()
                compact = _compact_action(a)
                if domain == "nutrition":
                    nutrition.append(compact)
                elif domain == "exercise":
                    exercise.append(compact)
        days.append(
            {
                "local_date": local_d.isoformat(),
                "day_index": i + 1,
                "nutrition": nutrition,
                "exercise": exercise,
            }
        )

    return {
        "cycle_start": cycle_start.isoformat(),
        "cycle_end": cycle_end.isoformat(),
        "timezone": tz_name,
        "state": state,
        "review_due": review_due,
        "days": days,
    }
