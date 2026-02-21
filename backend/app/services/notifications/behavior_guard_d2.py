# app/services/notifications/behavior_guard_d2.py
"""
D2.0 / D2.1 Behavior Guard for health_alert notifications (cooldown, quiet hours, reason).
Additive guard: does not change D1 ingestion or dedupe locks.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.models import NotificationGuardState
from backend.app.services.notification_runtime.quiet_hours import is_within_quiet_window

logger = logging.getLogger("sedi.behavior_guard")
if not logging.root.handlers:
    logging.basicConfig(level=logging.INFO)

HEALTH_ALERT_COOLDOWN_SECONDS = int(os.getenv("HEALTH_ALERT_COOLDOWN_SECONDS", "900"))


def _naive_utc(dt: datetime) -> datetime:
    """Normalize to naive UTC for DB comparison."""
    if dt.tzinfo:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@dataclass
class GuardDecision:
    allow: bool
    reason: str
    cooldown_until: Optional[datetime] = None


def _log_decision(
    user_id: int,
    channel: str,
    rule_id: str,
    severity: str,
    allow: bool,
    reason: str,
    cooldown_until: Optional[datetime],
    in_quiet: bool,
    trace_id: Optional[str] = None,
) -> None:
    """One line per decision for journal/stdout."""
    logger.info(
        "[D2_GUARD] user_id=%s channel=%s rule_id=%s severity=%s allow=%s reason=%s cooldown_until=%s in_quiet=%s trace=%s",
        user_id, channel, rule_id, severity, allow, reason, cooldown_until, in_quiet, trace_id or "",
    )


def evaluate_health_alert_guard(
    db: Session,
    user_id: int,
    channel: str,
    rule_id: str,
    severity: str,
    event_type: str,
    now_utc: datetime,
    trace_id: Optional[str] = None,
) -> GuardDecision:
    """
    Evaluate whether to allow creating a health_alert for this (user, channel, rule_id).
    D2.1: Quiet hours block when in_quiet and severity != "high"; high overrides quiet hours.
    Cooldown still applies after quiet-hours check. Row-level lock (FOR UPDATE) when row exists.
    """
    in_quiet = is_within_quiet_window(db, user_id)

    if in_quiet and severity != "high":
        _log_decision(user_id, channel, rule_id, severity, False, "quiet_hours", None, True, trace_id)
        return GuardDecision(allow=False, reason="quiet_hours", cooldown_until=None)

    row = (
        db.query(NotificationGuardState)
        .filter(
            NotificationGuardState.user_id == user_id,
            NotificationGuardState.channel == channel,
            NotificationGuardState.rule_id == rule_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        reason = "quiet_hours_override" if (in_quiet and severity == "high") else "first_send"
        _log_decision(user_id, channel, rule_id, severity, True, reason, None, in_quiet, trace_id)
        return GuardDecision(allow=True, reason=reason, cooldown_until=None)

    cooldown_until = row.cooldown_until
    now_naive = _naive_utc(now_utc)
    if cooldown_until is None or cooldown_until <= now_naive:
        reason = "quiet_hours_override" if (in_quiet and severity == "high") else "cooldown_expired"
        _log_decision(user_id, channel, rule_id, severity, True, reason, cooldown_until, in_quiet, trace_id)
        return GuardDecision(allow=True, reason=reason, cooldown_until=None)

    _log_decision(user_id, channel, rule_id, severity, False, "cooldown", cooldown_until, in_quiet, trace_id)
    return GuardDecision(allow=False, reason="cooldown", cooldown_until=cooldown_until)


def record_health_alert_sent(
    db: Session,
    user_id: int,
    channel: str,
    rule_id: str,
    now_utc: datetime,
    trace_id: Optional[str] = None,
) -> None:
    """
    Update guard state after a health_alert was successfully created.
    Locks existing row (FOR UPDATE) before update to remain correct under concurrency.
    """
    now_naive = _naive_utc(now_utc)
    delta = timedelta(seconds=HEALTH_ALERT_COOLDOWN_SECONDS)
    cooldown_until = now_naive + delta
    row = (
        db.query(NotificationGuardState)
        .filter(
            NotificationGuardState.user_id == user_id,
            NotificationGuardState.channel == channel,
            NotificationGuardState.rule_id == rule_id,
        )
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        row = NotificationGuardState(
            user_id=user_id,
            channel=channel,
            rule_id=rule_id,
            last_sent_at=now_naive,
            cooldown_until=cooldown_until,
            updated_at=now_naive,
        )
        db.add(row)
    else:
        row.last_sent_at = now_naive
        row.cooldown_until = cooldown_until
        row.updated_at = now_naive
    db.commit()
