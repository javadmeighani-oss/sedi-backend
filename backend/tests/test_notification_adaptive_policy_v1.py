# backend/tests/test_notification_adaptive_policy_v1.py
"""Tests for Adaptive Policy V1: companion cap, paused_until, precedence, open not triggering."""

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from backend.app.models import Notification, NotificationFeedback, User
from backend.app.services.notifications.adaptive_policy_v1 import (
    compute_adaptive_state,
    is_companion_send_allowed,
)
from backend.app.services.notification_engine import _count_companion_notifications_today


@pytest.fixture
def user(db):
    u = User(name="Adaptive User", secret_key="au", preferred_language="en", created_at=datetime.utcnow())
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


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


def test_two_dislikes_cap_override_one(db, user, notif):
    """2 dislikes -> companion_cap_override = 1."""
    _add_feedback(db, user.id, "dislike", notif.id)
    _add_feedback(db, user.id, "dislike", notif.id)
    now = datetime.utcnow()
    state = compute_adaptive_state(db, user.id, now, days=7)
    assert state["companion_cap_override"] == 1
    assert state["paused_until"] is None
    assert state["counts"]["dislike"] == 2


def test_three_dismiss_paused_until_set(db, user, notif):
    """3 dismiss -> paused_until set (now + 48h)."""
    _add_feedback(db, user.id, "dismiss", notif.id)
    _add_feedback(db, user.id, "dismiss", notif.id)
    _add_feedback(db, user.id, "dismiss", notif.id)
    now = datetime.utcnow()
    state = compute_adaptive_state(db, user.id, now, days=7)
    assert state["paused_until"] is not None
    assert state["counts"]["dismiss"] == 3
    allowed, reason = is_companion_send_allowed(db, user.id, now, days=7)
    assert allowed is False
    assert reason == "paused"


def test_two_likes_and_two_dislikes_precedence_cap(db, user, notif):
    """2 likes and 2 dislikes -> cap wins (precedence: pause > cap > like). companion_cap_override = 1."""
    _add_feedback(db, user.id, "like", notif.id)
    _add_feedback(db, user.id, "like", notif.id)
    _add_feedback(db, user.id, "dislike", notif.id)
    _add_feedback(db, user.id, "dislike", notif.id)
    now = datetime.utcnow()
    state = compute_adaptive_state(db, user.id, now, days=7)
    assert state["paused_until"] is None
    assert state["companion_cap_override"] == 1
    assert state["counts"]["like"] == 2
    assert state["counts"]["dislike"] == 2


def test_open_events_do_not_trigger_pause_or_cap(db, user, notif):
    """Only open events -> no pause, cap stays 2."""
    _add_feedback(db, user.id, "open", notif.id)
    _add_feedback(db, user.id, "open", notif.id)
    _add_feedback(db, user.id, "open", notif.id)
    now = datetime.utcnow()
    state = compute_adaptive_state(db, user.id, now, days=7)
    assert state["paused_until"] is None
    assert state["companion_cap_override"] == 2
    assert state["counts"]["open"] == 3
    allowed, reason = is_companion_send_allowed(db, user.id, now, days=7)
    assert allowed is True
    assert reason == ""


def test_count_companion_notifications_today_includes_both_dedupe_formats(db, user):
    """Companion cap count includes both canonical (companion:) and legacy (companion_*) dedupe_key formats."""
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    # Legacy format: template_key:user_id:date
    n1 = Notification(
        user_id=user.id,
        type="connection_ping",
        title="T1",
        body="B1",
        priority="normal",
        is_read=False,
        is_sent=False,
        created_at=now,
        dedupe_key=f"companion_daily_checkin_v1:{user.id}:{date_str}",
    )
    db.add(n1)
    # Canonical format: channel:template_key:user_id:date
    n2 = Notification(
        user_id=user.id,
        type="connection_ping",
        title="T2",
        body="B2",
        priority="normal",
        is_read=False,
        is_sent=False,
        created_at=now,
        dedupe_key=f"companion:companion_daily_checkin_v1:{user.id}:{date_str}",
    )
    db.add(n2)
    db.commit()
    count = _count_companion_notifications_today(db, user.id, now)
    assert count == 2
