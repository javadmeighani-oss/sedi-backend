# backend/tests/test_behavior_guard_d2.py
"""Unit tests for D2.0 / D2.1 Behavior Guard (health_alert cooldown + quiet hours)."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from backend.app.services.notifications.behavior_guard_d2 import (
    evaluate_health_alert_guard,
    record_health_alert_sent,
)


@pytest.fixture
def guard_user(db: Session):
    from backend.app.models import User
    u = User(
        name="Guard Test User",
        secret_key="guard-secret",
        preferred_language="en",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_first_time_allow_true(db: Session, guard_user) -> None:
    """First evaluation for (user, channel, rule_id) -> allow=True."""
    now = datetime.utcnow()
    decision = evaluate_health_alert_guard(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        severity="high",
        event_type="heart_rate",
        now_utc=now,
    )
    assert decision.allow is True
    assert decision.reason in ("first_send", "cooldown_expired")
    assert decision.cooldown_until is None


@patch("backend.app.services.notifications.behavior_guard_d2.HEALTH_ALERT_COOLDOWN_SECONDS", 900)
def test_second_within_cooldown_allow_false_reason_cooldown(db: Session, guard_user) -> None:
    """After recording a send, second evaluation within cooldown -> allow=False, reason=cooldown."""
    now = datetime.utcnow()
    record_health_alert_sent(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        now_utc=now,
    )
    decision = evaluate_health_alert_guard(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        severity="high",
        event_type="heart_rate",
        now_utc=now,
    )
    assert decision.allow is False
    assert decision.reason == "cooldown"
    assert decision.cooldown_until is not None


@patch("backend.app.services.notifications.behavior_guard_d2.HEALTH_ALERT_COOLDOWN_SECONDS", 2)
def test_after_cooldown_allow_true(db: Session, guard_user) -> None:
    """After cooldown expires, evaluation -> allow=True. No sleep: use injected now_utc."""
    t0 = datetime.utcnow()
    record_health_alert_sent(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        now_utc=t0,
    )
    # Evaluate at t0 + cooldown + 1s (past cooldown); guard reads monkeypatched 2s
    now_past_cooldown = t0 + timedelta(seconds=3)
    decision = evaluate_health_alert_guard(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        severity="high",
        event_type="heart_rate",
        now_utc=now_past_cooldown,
    )
    assert decision.allow is True
    assert decision.reason == "cooldown_expired"


@patch("backend.app.services.notifications.behavior_guard_d2.is_within_quiet_hours", return_value=True)
def test_quiet_hours_blocks_low_severity(
    _mock_qh,
    db: Session,
    guard_user,
) -> None:
    """When quiet hours helper returns True and severity is low => allow=False, reason=quiet_hours."""
    now = datetime.utcnow()
    decision = evaluate_health_alert_guard(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        severity="low",
        event_type="heart_rate",
        now_utc=now,
    )
    assert decision.allow is False
    assert decision.reason == "quiet_hours"
    assert decision.cooldown_until is None


@patch("backend.app.services.notifications.behavior_guard_d2.is_within_quiet_hours", return_value=True)
@patch("backend.app.services.notifications.behavior_guard_d2.HEALTH_ALERT_COOLDOWN_SECONDS", 900)
def test_quiet_hours_allows_high_but_cooldown_applies(
    _mock_qh,
    db: Session,
    guard_user,
) -> None:
    """Quiet hours True + severity high => not blocked by quiet hours; then cooldown row => allow=False reason=cooldown."""
    now = datetime.utcnow()
    record_health_alert_sent(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        now_utc=now,
    )
    decision = evaluate_health_alert_guard(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        severity="high",
        event_type="heart_rate",
        now_utc=now,
    )
    assert decision.allow is False
    assert decision.reason == "cooldown"
    assert decision.cooldown_until is not None
