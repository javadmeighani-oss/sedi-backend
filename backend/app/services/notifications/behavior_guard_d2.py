# app/services/notifications/behavior_guard_d2.py
"""
D2.0 Behavior Guard for health_alert notifications (cooldown + reason).
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

logger = logging.getLogger(__name__)

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


def evaluate_health_alert_guard(
    db: Session,
    user_id: int,
    channel: str,
    rule_id: str,
    severity: str,
    event_type: str,
    now_utc: datetime,
) -> GuardDecision:
    """
    Evaluate whether to allow creating a health_alert for this (user, channel, rule_id).
    Returns allow=True if no recent send within cooldown; else allow=False with reason.
    When a guard row exists, locks it (FOR UPDATE) to reduce race on concurrent ingests.
    """
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
        logger.info(
            "[D2_GUARD] user_id=%s channel=%s rule_id=%s allow=True reason=first_send cooldown_until=None",
            user_id, channel, rule_id,
        )
        return GuardDecision(allow=True, reason="first_send", cooldown_until=None)

    cooldown_until = row.cooldown_until
    now_naive = _naive_utc(now_utc)
    if cooldown_until is None or cooldown_until <= now_naive:
        logger.info(
            "[D2_GUARD] user_id=%s channel=%s rule_id=%s allow=True reason=cooldown_expired cooldown_until=%s",
            user_id, channel, rule_id, cooldown_until,
        )
        return GuardDecision(allow=True, reason="cooldown_expired", cooldown_until=None)

    # Still within cooldown
    logger.info(
        "[D2_GUARD] user_id=%s channel=%s rule_id=%s allow=False reason=cooldown cooldown_until=%s",
        user_id, channel, rule_id, cooldown_until,
    )
    return GuardDecision(allow=False, reason="cooldown", cooldown_until=cooldown_until)


def record_health_alert_sent(
    db: Session,
    user_id: int,
    channel: str,
    rule_id: str,
    now_utc: datetime,
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
