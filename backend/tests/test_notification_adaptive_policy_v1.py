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


def test_three_dismiss_never_pause_only_soften(db, user, notif):
    """R-023: 3 dismiss -> NO pause; the cap is softened to 1/day and the ignored hour is avoided."""
    _add_feedback(db, user.id, "dismiss", notif.id)
    _add_feedback(db, user.id, "dismiss", notif.id)
    _add_feedback(db, user.id, "dismiss", notif.id)
    now = datetime.utcnow()
    state = compute_adaptive_state(db, user.id, now, days=7)
    assert state["paused_until"] is None
    assert state["counts"]["dismiss"] == 3
    assert state["companion_cap_override"] == 1
    allowed, reason = is_companion_send_allowed(db, user.id, now, days=7)
    assert allowed is True
    assert reason == ""
    assert notif.created_at.hour in state["timing"]["avoid_hours_utc"]


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


# ---- R-009 / R-011: reasons shape the presence re-engagement family ----
def _add_reason_feedback(db: Session, user_id: int, notification_id: int, reason: str, action: str = "dislike"):
    import json

    db.add(
        NotificationFeedback(
            notification_id=notification_id,
            user_id=user_id,
            action=action,
            meta_json=json.dumps({"reason": reason}),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()


def test_too_frequent_and_wrong_timing_reasons_adapt_never_pause(db, user, notif):
    """R-023: too_frequent -> one a day; wrong_timing -> another time of day. Sending is never switched off."""
    now = datetime.utcnow()
    _add_reason_feedback(db, user.id, notif.id, "too_frequent")
    allowed, why = is_companion_send_allowed(db, user.id, now)
    st = compute_adaptive_state(db, user.id, now)
    assert allowed is True and why == ""
    assert st["paused_until"] is None and st["companion_cap_override"] == 1
    db.query(NotificationFeedback).delete()
    db.commit()
    _add_reason_feedback(db, user.id, notif.id, "wrong_timing")
    allowed, why = is_companion_send_allowed(db, user.id, now)
    st = compute_adaptive_state(db, user.id, now)
    assert allowed is True and st["paused_until"] is None
    assert st["timing"]["wrong_timing"] is True
    band = {(notif.created_at.hour + d) % 24 for d in (-1, 0, 1)}
    assert set(st["timing"]["avoid_hours_utc"]) == band


def test_avoided_hours_are_capped_so_the_day_is_never_muted(db, user):
    now = datetime.utcnow()
    for h in (1, 5, 9, 13, 17, 21):
        n = Notification(
            user_id=user.id, type="connection_ping", title="T", body="B", priority="normal",
            is_read=False, is_sent=True, created_at=now.replace(hour=h, minute=0, second=0, microsecond=0),
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        _add_reason_feedback(db, user.id, n.id, "wrong_timing")
    st = compute_adaptive_state(db, user.id, now)
    assert len(st["timing"]["avoid_hours_utc"]) <= 9


def test_irrelevant_and_unclear_reasons_change_content_not_frequency(db, user, notif):
    _add_reason_feedback(db, user.id, notif.id, "irrelevant")
    st = compute_adaptive_state(db, user.id, datetime.utcnow())
    assert st["content_hints"] == {"avoid_topic": True, "simple_copy": False, "lighter_touch": False}
    assert st["paused_until"] is None
    _add_reason_feedback(db, user.id, notif.id, "unclear")
    st = compute_adaptive_state(db, user.id, datetime.utcnow())
    assert st["content_hints"]["simple_copy"] is True and st["paused_until"] is None


def test_three_dislikes_change_the_style_not_the_sending(db, user, notif):
    """R-023: many dislikes -> lighter touch (plain check-in, no topic recap); never a pause."""
    for _ in range(3):
        _add_feedback(db, user.id, "dislike", notif.id)
    now = datetime.utcnow()
    st = compute_adaptive_state(db, user.id, now)
    assert st["paused_until"] is None
    assert st["content_hints"]["lighter_touch"] is True
    assert is_companion_send_allowed(db, user.id, now) == (True, "")


def test_simple_copy_hint_uses_plainest_engagement_wording():
    from backend.app.services.notification_runtime.renderer import _ENGAGEMENT_PAIRS, render

    out = render("engagement", "fa", {"simple_copy": True}, "low")
    assert (out["title"], out["body"].strip()) == (_ENGAGEMENT_PAIRS["fa"][0][0], _ENGAGEMENT_PAIRS["fa"][0][1].format(p="").strip())
