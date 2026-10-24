"""R-019: the care check-in runs INSIDE the smart-notification framework (I10 queue, send guard, reactions, tap-through)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services import a3_session_open as so
from backend.app.services.i10.contextual_followup_worker import process_due_follow_up_tasks
from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


@pytest.fixture(autouse=True)
def _flag_and_policy():
    with patch(
        "backend.app.services.i10.contextual_followup_worker.contextual_followup_enabled", return_value=True
    ), patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy", return_value=(True, {})
    ), patch(
        "backend.app.services.notification_runtime.quiet_hours.is_within_quiet_hours", return_value=False
    ):
        yield


def _scheduled_user(db, phone):
    u = _user(db, phone, tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    _seed_consent(db, u.id)
    from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account

    ensure_self_subject_for_account(db, u.id, commit=True)
    process_message(db, u.id, "مادرم دیروز فوت کرد", "fa")
    task = db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).one()
    task.due_at = datetime.utcnow() - timedelta(minutes=5)
    db.commit()
    return u, task


def test_due_checkin_is_a_normal_smart_notification(db):
    u, task = _scheduled_user(db, "+17770019001")
    assert process_due_follow_up_tasks(db) == 1
    n = db.query(models.Notification).filter(models.Notification.user_id == u.id).one()
    assert n.type == "connection_ping" and n.template_key == "care_checkin"
    assert n.category == "care_follow_up" and n.source_type == "care_follow_up_task"
    assert n.i10_policy_decision_id is not None  # went through the I10 policy/ledger, not a side path
    assert n.body.startswith("جواد جان، ") and "فوت" not in (n.body + n.title)
    db.refresh(task)
    assert task.status == "notified"


def test_user_reactions_pause_the_checkin_like_any_companion_ping(db):
    u, task = _scheduled_user(db, "+17770019002")
    # three recent dislikes -> adaptive policy pauses companion-style pings for 48h
    seed = models.Notification(user_id=u.id, type="connection_ping", title="x", body="y", channel="push", status="sent")
    db.add(seed)
    db.flush()
    for _ in range(3):
        db.add(models.NotificationFeedback(notification_id=seed.id, user_id=u.id, action="dislike", created_at=datetime.utcnow()))
    db.commit()
    assert process_due_follow_up_tasks(db) == 0
    db.refresh(task)
    assert task.status == "open"  # waits, nothing sent
    assert db.query(models.Notification).filter(models.Notification.template_key == "care_checkin").count() == 0


def test_a_checkin_that_could_not_be_sent_for_a_week_is_dropped(db):
    u, task = _scheduled_user(db, "+17770019003")
    task.due_at = datetime.utcnow() - timedelta(days=8)
    seed = models.Notification(user_id=u.id, type="connection_ping", title="x", body="y", channel="push", status="sent")
    db.add(seed)
    db.flush()
    for _ in range(3):
        db.add(models.NotificationFeedback(notification_id=seed.id, user_id=u.id, action="dislike", created_at=datetime.utcnow()))
    db.commit()
    process_due_follow_up_tasks(db)
    db.refresh(task)
    assert task.status == "cancelled"


def test_tapping_the_checkin_opens_a_warm_opener_without_naming_the_event(db):
    u, _task = _scheduled_user(db, "+17770019004")
    process_due_follow_up_tasks(db)
    n = db.query(models.Notification).filter(models.Notification.template_key == "care_checkin").one()
    text = so.build_notification_origin_opener(db, u, n, language="fa")
    assert text.startswith("جواد جان، خوشحالم که اومدی") and "فوت" not in text and "مادر" not in text
