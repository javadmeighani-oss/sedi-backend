"""R-021 / M5: Sedi's daily initiative — one gentle, memory-based message per day through the smart-notification framework."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services import a3_session_open as so
from backend.app.services.i10.contextual_followup_worker import process_due_follow_up_tasks
from backend.app.services.i10.daily_initiative import choose_initiative, run_daily_initiative_sweep
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
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


def _user_with_concern(db, phone):
    u = _user(db, phone, tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    _seed_consent(db, u.id)
    ensure_self_subject_for_account(db, u.id, commit=True)
    process_message(db, u.id, "من دیابت دارم", "fa")
    return u


def test_nothing_known_means_silence(db):
    u = _user(db, "+17770024001", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    assert choose_initiative(db, u.id) is None
    assert run_daily_initiative_sweep(db) == 0


def test_sweep_creates_one_task_a_day_and_respects_recent_chat(db):
    u = _user_with_concern(db, "+17770024002")
    assert choose_initiative(db, u.id) == "health"
    now = datetime.utcnow()
    db.add(models.Memory(user_id=u.id, user_message="سلام", sedi_response="سلام", language="fa", created_at=now - timedelta(hours=1)))
    db.commit()
    assert run_daily_initiative_sweep(db, now=now) == 0  # they were just talking
    assert run_daily_initiative_sweep(db, now=now + timedelta(hours=8)) == 1
    assert run_daily_initiative_sweep(db, now=now + timedelta(hours=9)) == 0  # once a day
    tasks = db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).all()
    assert [t.title for t in tasks] == ["initiative:health"]


def test_delivery_goes_through_the_smart_notification_framework_and_never_names_the_condition(db):
    u = _user_with_concern(db, "+17770024003")
    db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).delete()
    db.commit()
    assert run_daily_initiative_sweep(db) == 1
    assert process_due_follow_up_tasks(db) == 1
    n = db.query(models.Notification).filter(models.Notification.template_key == "daily_initiative").one()
    assert n.type == "connection_ping" and n.category == "care_follow_up" and n.i10_policy_decision_id is not None
    assert n.body.startswith("جواد جان، ") and "دیابت" not in n.body and "دیابت" not in n.title
    opener = so.build_notification_origin_opener(db, u, n, language="fa")
    assert opener.startswith("جواد جان، خوشحالم که اومدی")


def test_user_reactions_pause_the_initiative(db):
    u = _user_with_concern(db, "+17770024004")
    assert run_daily_initiative_sweep(db) == 1
    seed = models.Notification(user_id=u.id, type="connection_ping", title="x", body="y", channel="push", status="sent")
    db.add(seed)
    db.flush()
    for _ in range(3):
        db.add(models.NotificationFeedback(notification_id=seed.id, user_id=u.id, action="dislike", created_at=datetime.utcnow()))
    db.commit()
    assert process_due_follow_up_tasks(db) == 0
    assert db.query(models.Notification).filter(models.Notification.template_key == "daily_initiative").count() == 0


def test_suggestion_followup_is_preferred_over_the_generic_health_check(db):
    u = _user_with_concern(db, "+17770024005")
    now = datetime.utcnow()
    db.add(models.Memory(user_id=u.id, user_message="خوابم نمیاد", sedi_response="پیشنهاد می‌کنم قبل از خواب نفس عمیق بکش.", language="fa", created_at=now - timedelta(days=2)))
    for i in range(10):
        db.add(models.Memory(user_id=u.id, user_message=f"پیام {i} امروز", sedi_response="باشه", language="fa", created_at=now - timedelta(hours=30 - i)))
    db.commit()
    assert choose_initiative(db, u.id) == "suggestion"
