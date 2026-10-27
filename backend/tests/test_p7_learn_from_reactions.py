"""P7 (2026-10-27): Sedi learns from notification reactions even when the user gives no reason.

Javad: «وقتی نوتیف پیگیری ارسال می‌کند و کاربر می‌گوید نمی‌پسندم، صدی باید دلیل را متوجه شود تا خود را اصلاح کند.»
The tray's Dislike button carries no reason, so adaptive_policy_v1 now infers it from evidence, and the contextual
follow-up copy (now in the user's language) obeys the learned hints.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from backend.app import models
from backend.app.services.i10.contextual_followup_i10_adapter import render_followup_copy
from backend.app.services.notifications.adaptive_policy_v1 import compute_adaptive_state, infer_dislike_reasons
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _user

NOW = datetime(2026, 10, 27, 12, 0)  # naive UTC


def _note(db, user, *, hour_utc, template_key=None, category=None, n=0):
    """A sent notification at ``hour_utc`` today (Tehran = UTC+3:30)."""
    stamp = NOW.replace(hour=hour_utc, minute=0) + timedelta(seconds=n)
    row = models.Notification(
        user_id=user.id,
        type="connection_ping",
        body="x",
        priority="normal",
        is_sent=True,
        sent_at=stamp,
        created_at=stamp,
        template_key=template_key,
        category=category,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _react(db, user, note, action="dislike", reason=None):
    meta = {"canonical_verb": "DISLIKE_REASON" if reason else "DISLIKE.upper"}
    if reason:
        meta["reason"] = reason
    db.add(
        models.NotificationFeedback(
            notification_id=note.id,
            user_id=user.id,
            action=action,
            meta_json=json.dumps(meta),
            created_at=NOW - timedelta(minutes=5),
        )
    )
    db.commit()


def test_dislike_at_night_means_wrong_timing_and_the_hour_is_avoided(db):
    u = _user(db, "+17770031001", tz="Asia/Tehran")
    n = _note(db, u, hour_utc=19)  # 22:30 Tehran
    assert infer_dislike_reasons(db, u.id, n) == ["wrong_timing"]
    _react(db, u, n)  # ONE dislike, no reason given
    st = compute_adaptive_state(db, u.id, NOW)
    assert st["timing"]["wrong_timing"] is True
    assert 19 in st["timing"]["avoid_hours_utc"]
    assert st["inferred_reasons_count"] == {"wrong_timing": 1}
    assert st["paused_until"] is None  # adapt, never stop (R-023)


def test_many_notifications_that_day_means_too_frequent(db):
    u = _user(db, "+17770031002", tz="Asia/Tehran")
    _note(db, u, hour_utc=5, n=1)
    _note(db, u, hour_utc=6, n=2)
    last = _note(db, u, hour_utc=8, n=3)  # 11:30 Tehran, the third in a few hours
    assert infer_dislike_reasons(db, u.id, last) == ["too_frequent"]
    _react(db, u, last)
    assert compute_adaptive_state(db, u.id, NOW)["companion_cap_override"] == 1


def test_a_disliked_follow_up_means_do_not_repeat_the_topic(db):
    u = _user(db, "+17770031003", tz="Asia/Tehran")
    n = _note(db, u, hour_utc=8, template_key="contextual_follow_up")
    assert infer_dislike_reasons(db, u.id, n) == ["irrelevant"]
    _react(db, u, n)
    assert compute_adaptive_state(db, u.id, NOW)["content_hints"]["avoid_topic"] is True


def test_unknown_reason_still_changes_the_wording_after_one_dislike(db):
    u = _user(db, "+17770031004", tz="Asia/Tehran")
    n = _note(db, u, hour_utc=8)
    assert infer_dislike_reasons(db, u.id, n) == ["not_helpful", "unclear"]
    _react(db, u, n)
    hints = compute_adaptive_state(db, u.id, NOW)["content_hints"]
    assert hints["avoid_topic"] is True and hints["simple_copy"] is True


def test_the_users_own_reason_wins_over_the_inference(db):
    u = _user(db, "+17770031005", tz="Asia/Tehran")
    n = _note(db, u, hour_utc=19)  # night -> would be inferred as wrong_timing
    _react(db, u, n)  # tray dislike, no reason
    _react(db, u, n, reason="unclear")  # then the user says why
    st = compute_adaptive_state(db, u.id, NOW)
    assert st["inferred_reasons_count"] == {}
    assert st["reasons_count"] == {"unclear": 1}
    assert st["timing"]["wrong_timing"] is False
    assert st["content_hints"]["simple_copy"] is True


def test_no_reaction_changes_nothing(db):
    u = _user(db, "+17770031006", tz="Asia/Tehran")
    st = compute_adaptive_state(db, u.id, NOW)
    assert st["content_hints"] == {"avoid_topic": False, "simple_copy": False, "lighter_touch": False}
    assert st["inferred_reasons_count"] == {}


def _followup_task(db, user, title="مرور برنامه ورزش"):
    task = models.CareFollowUpTask(
        user_id=user.id,
        title=title,
        description="",
        status="open",
        source="general_ctx",
        due_at=NOW,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_followup_copy_is_localised_and_gentler_after_a_dislike(db):
    u = _user(db, "+17770031007", tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    db.commit()
    task = _followup_task(db, u)
    title, body, key = render_followup_copy(db, task)
    assert title == "صدی" and key == "contextual_follow_up"
    assert "جواد جان" in body and "مرور برنامه ورزش" in body  # before any reaction: with the topic

    n = _note(db, u, hour_utc=8, template_key="contextual_follow_up")
    _react(db, u, n)
    # compute_adaptive_state looks 7 days back from "now": make the reaction recent for the renderer
    row = db.query(models.NotificationFeedback).filter(models.NotificationFeedback.user_id == u.id).one()
    row.created_at = datetime.utcnow()
    n.sent_at = n.created_at = datetime.utcnow().replace(hour=8, minute=0)
    db.commit()
    _title, gentle, _key = render_followup_copy(db, task)
    assert "مرور برنامه ورزش" not in gentle  # the user did not want the topic again
    assert "جواد جان" in gentle and "من اینجام" in gentle


def test_followup_copy_for_english_users_is_unchanged(db):
    u = _user(db, "+17770031008", tz="Asia/Tehran")
    u.preferred_language = "en"
    db.commit()
    task = _followup_task(db, u, "my exercise plan")
    title, body, key = render_followup_copy(db, task)
    assert title == "Continuing our conversation" and "my exercise plan" in body
