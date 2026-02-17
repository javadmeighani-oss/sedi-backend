# backend/app/behavior/policy.py
"""Behavior Layer V1: policy for when to allow initiation and add lead-in (deterministic, testable)."""
from datetime import date, datetime, timedelta, time
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app.behavior.models import BehaviorMode, score_to_mode
from backend.app.behavior.config import (
    get_daily_engagement_budget,
    get_cooldown_minutes,
    get_quiet_hours_use_notification_runtime,
)
from backend.app.services.notification_runtime.quiet_hours import is_within_quiet_hours


def _today_utc(now: datetime) -> date:
    if hasattr(now, "date"):
        return now.date()
    return date(now.year, now.month, now.day)


class BehaviorPolicy:
    """
    Deterministic policy: quiet hours, daily cap, cooldown.
    Does not read BEHAVIOR_V1_ENABLED; caller must skip when disabled.
    """

    def __init__(
        self,
        daily_budget: Optional[int] = None,
        cooldown_minutes: Optional[int] = None,
        use_quiet_hours_runtime: bool = True,
    ):
        self.daily_budget = daily_budget if daily_budget is not None else get_daily_engagement_budget()
        self.cooldown_minutes = cooldown_minutes if cooldown_minutes is not None else get_cooldown_minutes()
        self.use_quiet_hours_runtime = use_quiet_hours_runtime

    def mode_from_score(self, score: float) -> BehaviorMode:
        """Deterministic score -> mode mapping."""
        return score_to_mode(score)

    def can_initiate(
        self,
        db: Session,
        user_id: int,
        now: datetime,
        daily_initiated_count: int,
        last_initiated_at: Optional[datetime],
        day_start_utc: Optional[date] = None,
        initiated_today: bool = False,
    ) -> Tuple[bool, str]:
        """
        Returns (allowed, reason_string).
        Checks: 1) initiated_today, 2) daily cap, 3) cooldown, 4) quiet hours (engagement channel).
        initiated_today: True when last_initiated_at is not null and same user-local calendar day as now (caller computes).
        """
        # 1) Already initiated today (block regardless of daily_initiated_count)
        if initiated_today:
            return False, "initiated_today"

        # 2) Daily cap
        if daily_initiated_count >= self.daily_budget:
            return False, "daily_cap"

        # 3) Cooldown
        if last_initiated_at is not None:
            cooldown_end = last_initiated_at + timedelta(minutes=self.cooldown_minutes)
            if now < cooldown_end:
                return False, "cooldown"

        # 4) Quiet hours (reuse notification runtime)
        if self.use_quiet_hours_runtime:
            if is_within_quiet_hours(db, user_id, "engagement", "normal"):
                return False, "quiet_hours"

        return True, ""

    def should_add_lead_in(self, mode: BehaviorMode, question_type: Optional[str] = None) -> bool:
        """When True, caller may prepend caring lead-in. Normal/high add lead-in for confirm/profile."""
        if mode == BehaviorMode.low:
            return False
        if mode == BehaviorMode.high:
            return True
        # normal: add for confirm_candidate
        return (question_type or "").strip().lower() == "confirm_candidate"
