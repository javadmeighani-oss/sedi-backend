"""Policy-driven proactive interaction foundation — default off."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags


@dataclass(frozen=True)
class ProactivePolicy:
    cooldown_minutes: int
    max_per_day: int
    quiet_hours_start: Optional[int]
    quiet_hours_end: Optional[int]
    reason_codes: frozenset

    @classmethod
    def from_env(cls) -> "ProactivePolicy":
        def _int(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, str(default)))
            except ValueError:
                return default

        def _opt_hour(name: str) -> Optional[int]:
            raw = os.environ.get(name, "").strip()
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        return cls(
            cooldown_minutes=_int("SEDI_PROACTIVE_COOLDOWN_MIN", 180),
            max_per_day=_int("SEDI_PROACTIVE_MAX_PER_DAY", 3),
            quiet_hours_start=_opt_hour("SEDI_PROACTIVE_QUIET_START_HOUR"),
            quiet_hours_end=_opt_hour("SEDI_PROACTIVE_QUIET_END_HOUR"),
            reason_codes=frozenset({
                "scheduled_plan",
                "care_followup",
                "medication_reminder",
                "appointment",
                "lifestyle_reminder",
                "notification_feedback",
                "user_inactivity",
                "device_freshness",
            }),
        )


def _in_quiet_hours(now: datetime, policy: ProactivePolicy, user_tz_hour: int) -> bool:
    if policy.quiet_hours_start is None or policy.quiet_hours_end is None:
        return False
    start, end = policy.quiet_hours_start, policy.quiet_hours_end
    if start <= end:
        return start <= user_tz_hour < end
    return user_tz_hour >= start or user_tz_hour < end


def should_create_proactive_notification(
    db: Session,
    user_id: int,
    reason_code: str,
    *,
    policy: Optional[ProactivePolicy] = None,
    user_tz_hour: int = 12,
) -> Dict[str, Any]:
    pol = policy or ProactivePolicy.from_env()
    if not feature_flags.proactive_interaction_enabled():
        return {"allowed": False, "reason": "flag_disabled"}
    if reason_code not in pol.reason_codes:
        return {"allowed": False, "reason": "unknown_reason_code"}
    if _in_quiet_hours(datetime.utcnow(), pol, user_tz_hour):
        return {"allowed": False, "reason": "quiet_hours"}

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count_today = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.created_at >= today_start,
            models.Notification.type == "proactive_care",
        )
        .count()
    )
    if count_today >= pol.max_per_day:
        return {"allowed": False, "reason": "daily_cap"}

    cooldown_since = datetime.utcnow() - timedelta(minutes=pol.cooldown_minutes)
    recent = (
        db.query(models.Notification)
        .filter(
            models.Notification.user_id == user_id,
            models.Notification.type == "proactive_care",
            models.Notification.created_at >= cooldown_since,
        )
        .first()
    )
    if recent:
        return {"allowed": False, "reason": "cooldown"}

    return {"allowed": True, "reason": reason_code}
