# backend/tests/test_notification_send_guard_v1.py
"""Tests for Send Guard V1: paused, quiet_hours, dedup, cap, critical health_alert bypass."""

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from backend.app.models import Notification, NotificationFeedback, User
from backend.app.services.notifications.send_guard_v1 import can_send_v1


@pytest.fixture
def user(db):
    u = User(
        name="Guard User",
        secret_key="gu",
        preferred_language="en",
        created_at=datetime.utcnow(),
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _add_feedback(db: Session, user_id: int, action: str, notification_id: int):
    f = NotificationFeedback(
        notification_id=notification_id,
        user_id=user_id,
        action=action,
        meta_json=None,
        created_at=datetime.utcnow(),
    )
    db.add(f)
    db.commit()


@pytest.fixture
def notif(db, user):
    n = Notification(
        user_id=user.id,
        type="connection_ping",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=False,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def test_dismissals_never_pause_companion_they_shift_the_time(db, user, notif):
    """R-023: 3 dismissals -> never 'paused'. The hour that was ignored is skipped, any other hour sends."""
    _add_feedback(db, user.id, "dismiss", notif.id)
    _add_feedback(db, user.id, "dismiss", notif.id)
    _add_feedback(db, user.id, "dismiss", notif.id)
    bad_hour = notif.created_at.hour
    day = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    in_bad = day.replace(hour=bad_hour)
    far = day.replace(hour=(bad_hour + 12) % 24)
    blocked = can_send_v1(db, user.id, "companion", "companion_daily_checkin_v1", "normal", in_bad)
    assert "paused" not in blocked["reasons"] and blocked.get("paused_until") is None
    assert "timing" in blocked["reasons"]
    ok = can_send_v1(db, user.id, "companion", "companion_daily_checkin_v1", "normal", far)
    assert "paused" not in ok["reasons"] and "timing" not in ok["reasons"]


def test_quiet_hours_blocks_companion(db, user):
    """When within quiet hours, companion send blocked with reason quiet_hours."""
    now = datetime.utcnow()
    with patch(
        "backend.app.services.notifications.send_guard_v1.is_within_quiet_hours",
        return_value=True,
    ):
        result = can_send_v1(
            db, user.id, "companion", "companion_daily_checkin_v1", "normal", now,
        )
    assert result["allowed"] is False
    assert "quiet_hours" in result["reasons"]


def test_dedup_blocks_second_send(db, user):
    """Existing Notification with same dedupe_key -> can_send_v1 returns dedup reason."""
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    dedupe_key = f"companion:companion_daily_checkin_v1:{user.id}:{date_str}"
    existing = Notification(
        user_id=user.id,
        type="connection_ping",
        title="T",
        body="B",
        priority="normal",
        is_read=False,
        is_sent=False,
        created_at=now,
        dedupe_key=dedupe_key,
    )
    db.add(existing)
    db.commit()
    result = can_send_v1(
        db, user.id, "companion", "companion_daily_checkin_v1", "normal", now,
    )
    assert result["allowed"] is False
    assert "dedup" in result["reasons"]
    assert result.get("dedupe_key") == dedupe_key


def test_cap_blocks_after_two_sends(db, user):
    """Two companion notifications today -> next send blocked with reason cap."""
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    for i in range(2):
        n = Notification(
            user_id=user.id,
            type="connection_ping",
            title=f"T{i}",
            body=f"B{i}",
            priority="normal",
            is_read=False,
            is_sent=False,
            created_at=now,
            dedupe_key=f"companion:companion_daily_checkin_v1:{user.id}:{date_str}:{i}",
        )
        db.add(n)
    db.commit()
    result = can_send_v1(
        db, user.id, "companion", "companion_daily_checkin_v1", "normal", now,
    )
    assert result["allowed"] is False
    assert "cap" in result["reasons"]
    assert result.get("cap") == 2


def test_critical_health_alert_bypasses_quiet_hours(db, user):
    """Inside quiet hours, health_alert + priority critical -> allowed True, no quiet_hours reason."""
    now = datetime.utcnow()
    with patch(
        "backend.app.services.notifications.send_guard_v1.is_within_quiet_hours",
        return_value=True,
    ):
        result = can_send_v1(
            db,
            user.id,
            "health_alert",
            "health_alert_generic_v1",
            "critical",
            now,
        )
    assert result["allowed"] is True
    assert "quiet_hours" not in result["reasons"]
