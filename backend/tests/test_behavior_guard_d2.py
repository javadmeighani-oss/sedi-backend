# backend/tests/test_behavior_guard_d2.py
"""Unit tests for D2.0 Behavior Guard (health_alert cooldown)."""

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


@patch("backend.app.services.notifications.behavior_guard_d2.HEALTH_ALERT_COOLDOWN_SECONDS", 1)
def test_after_cooldown_allow_true(db: Session, guard_user) -> None:
    """After cooldown expires, evaluation -> allow=True."""
    import time
    now = datetime.utcnow()
    record_health_alert_sent(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        now_utc=now,
    )
    time.sleep(1.1)
    now_later = datetime.utcnow()
    decision = evaluate_health_alert_guard(
        db=db,
        user_id=guard_user.id,
        channel="health_alert",
        rule_id="heart_rate_high",
        severity="high",
        event_type="heart_rate",
        now_utc=now_later,
    )
    assert decision.allow is True
    assert decision.reason == "cooldown_expired"
