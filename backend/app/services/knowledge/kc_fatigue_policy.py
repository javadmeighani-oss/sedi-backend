# app/services/knowledge/kc_fatigue_policy.py
"""Question Fatigue Control V1: daily cap, cooldown, burst guard, reject-streak escalation."""
import os
from datetime import datetime, date, timedelta, time
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models


def _get_daily_cap() -> int:
    return int(os.environ.get("KC_DAILY_QUESTION_CAP", "3"))


def _get_cooldown_minutes() -> int:
    return int(os.environ.get("KC_COOLDOWN_MINUTES", "90"))


def _get_burst_guard_minutes() -> int:
    return int(os.environ.get("KC_BURST_GUARD_MINUTES", "10"))


def _get_reject_streak_limit() -> int:
    return int(os.environ.get("KC_REJECT_STREAK_LIMIT", "2"))


def _get_block_until_hour_utc() -> int:
    return int(os.environ.get("KC_BLOCK_UNTIL_HOUR_UTC", "8"))


def _today_utc(now: datetime) -> date:
    if hasattr(now, "date"):
        return now.date()
    return date(now.year, now.month, now.day)


def _next_day_at_hour_utc(now: datetime, hour: int) -> datetime:
    """Return next calendar day at hour:00 UTC as naive datetime."""
    d = _today_utc(now) + timedelta(days=1)
    return datetime.combine(d, time(hour, 0, 0))


def ensure_state(db: Session, user_id: int, now: datetime) -> models.KcQuestionPolicyState:
    """Ensure policy state row exists; reset day-specific fields if day changed."""
    row = db.query(models.KcQuestionPolicyState).filter(
        models.KcQuestionPolicyState.user_id == user_id,
    ).first()
    today = _today_utc(now)
    if not row:
        row = models.KcQuestionPolicyState(
            user_id=user_id,
            day=today,
            asked_count=0,
            consecutive_rejects=0,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    if row.day != today:
        row.day = today
        row.asked_count = 0
        row.consecutive_rejects = 0
        row.cooldown_until = None
        row.last_question_type = None
        db.commit()
        db.refresh(row)
    return row


def _state_snapshot(
    state: models.KcQuestionPolicyState,
    daily_cap: int,
    next_eligible_at: Optional[datetime],
) -> Dict[str, Any]:
    return {
        "asked_today": state.asked_count,
        "daily_cap": daily_cap,
        "cooldown_until": state.cooldown_until.isoformat() if state.cooldown_until else None,
        "consecutive_rejects": state.consecutive_rejects,
        "next_eligible_at": next_eligible_at.isoformat() if next_eligible_at else None,
    }


def check_can_ask(
    db: Session,
    user_id: int,
    now: datetime,
) -> Tuple[bool, Optional[str], Optional[datetime], Dict[str, Any]]:
    """
    Returns (allowed, reason, next_eligible_at, state_snapshot).
    If not allowed, reason is set and next_eligible_at when the user can ask again.
    """
    state = ensure_state(db, user_id, now)
    daily_cap = _get_daily_cap()
    cooldown_min = _get_cooldown_minutes()
    burst_min = _get_burst_guard_minutes()
    block_hour = _get_block_until_hour_utc()

    next_eligible_at: Optional[datetime] = None

    # 1) Daily cap
    if state.asked_count >= daily_cap:
        next_eligible_at = _next_day_at_hour_utc(now, block_hour)
        snap = _state_snapshot(state, daily_cap, next_eligible_at)
        return False, "fatigue_control", next_eligible_at, snap

    # 2) Explicit cooldown_until (e.g. reject-streak block)
    if state.cooldown_until and now < state.cooldown_until:
        next_eligible_at = state.cooldown_until
        snap = _state_snapshot(state, daily_cap, next_eligible_at)
        return False, "fatigue_control", next_eligible_at, snap

    # 3) Burst guard
    if state.last_asked_at:
        burst_end = state.last_asked_at + timedelta(minutes=burst_min)
        if now < burst_end:
            next_eligible_at = burst_end
            snap = _state_snapshot(state, daily_cap, next_eligible_at)
            return False, "fatigue_control", next_eligible_at, snap

    # 4) Cooldown between questions
    if state.last_asked_at:
        cooldown_end = state.last_asked_at + timedelta(minutes=cooldown_min)
        if now < cooldown_end:
            next_eligible_at = cooldown_end
            snap = _state_snapshot(state, daily_cap, next_eligible_at)
            return False, "fatigue_control", next_eligible_at, snap

    snap = _state_snapshot(state, daily_cap, None)
    return True, None, None, snap


def mark_asked(db: Session, user_id: int, now: datetime, question_type: str) -> None:
    """Increment asked_count and set last_asked_at, last_question_type."""
    state = ensure_state(db, user_id, now)
    state.asked_count += 1
    state.last_asked_at = now
    state.last_question_type = question_type or None
    db.commit()


def mark_answer(
    db: Session,
    user_id: int,
    now: datetime,
    outcome: str,
) -> None:
    """
    outcome: 'accepted' | 'rejected' | 'skipped'
    On accepted: consecutive_rejects = 0.
    On rejected/skipped: consecutive_rejects += 1; if >= limit, set cooldown_until = next day 08:00 UTC.
    """
    state = ensure_state(db, user_id, now)
    limit = _get_reject_streak_limit()
    block_hour = _get_block_until_hour_utc()

    if outcome == "accepted":
        state.consecutive_rejects = 0
        db.commit()
        return
    if outcome in ("rejected", "skipped"):
        state.consecutive_rejects = (state.consecutive_rejects or 0) + 1
        if state.consecutive_rejects >= limit:
            state.cooldown_until = _next_day_at_hour_utc(now, block_hour)
        db.commit()
        return
