"""R-018: gentle care check-in after significant life events + continuity of care in chat (no new storage)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app import models
from backend.app.services.intelligence import care_continuity as cc
from backend.app.services.knowledge.conversation_extraction_service import process_message
from backend.app.services.knowledge.stated_facts_extractor_v1 import extract_care_events
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


def _kinds(text):
    return [(e.fact_value, e.confidence) for e in extract_care_events(text)]


def test_significant_events_are_detected_only_when_stated():
    assert _kinds("مادرم دیروز فوت کرد") == [("loss", 0.88)]
    assert _kinds("اخراج شدم") == [("job_loss", 0.88)]
    assert _kinds("my father passed away") == [("loss", 0.88)]
    assert _kinds("فکر کنم اخراج شدم")[0][1] < 0.85  # hedged -> never auto-accepted
    for text in ("آیا مادرم فوت کرد؟", "اگه اخراج بشم چی می‌شه", "امروز هوا خوبه"):
        assert _kinds(text) == []


def test_event_schedules_one_checkin_with_event_kind_only(db):
    u = _user(db, "+17770018001", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    process_message(db, u.id, "مادرم دیروز فوت کرد", "fa")
    process_message(db, u.id, "همسرم رو هم از دست دادم", "fa")  # same week -> deduped, no second check-in
    tasks = db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).all()
    assert len(tasks) == 1
    t = tasks[0]
    assert t.title == "care_checkin:loss" and t.status == "open" and t.source == "general_ctx"
    assert timedelta(days=1) < t.due_at - datetime.utcnow() <= timedelta(days=2, minutes=1)
    # the candidate is handled, not left pending for a confirmation question
    pending = db.query(models.KcFactCandidate).filter(
        models.KcFactCandidate.user_id == u.id, models.KcFactCandidate.status == "pending"
    ).count()
    assert pending == 0


def test_no_checkin_without_memory_consent(db):
    u = _user(db, "+17770018002", tz="Asia/Tehran")  # no consent
    process_message(db, u.id, "اخراج شدم", "fa")
    assert db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).count() == 0


def test_checkin_copy_is_warm_localised_and_never_names_the_event(db):
    from backend.app.services.i10.contextual_followup_i10_adapter import render_followup_copy

    u = _user(db, "+17770018003", tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    _seed_consent(db, u.id)
    process_message(db, u.id, "مادرم فوت کرد", "fa")
    task = db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == u.id).one()
    title, body, key = render_followup_copy(db, task)
    assert key == "care_checkin" and title == "صدی" and body.startswith("جواد جان، ")
    for leaked in ("فوت", "مادر", "loss", "care_checkin"):
        assert leaked not in body and leaked not in title


def test_chat_hint_mentions_recent_event_and_earlier_suggestions(db):
    u = _user(db, "+17770018004", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    process_message(db, u.id, "اخراج شدم", "fa")
    now = datetime.utcnow()
    # 12 newer turns push the old suggestion out of the 8-turn history window
    db.add(models.Memory(user_id=u.id, user_message="خوابم نمیاد", sedi_response="پیشنهاد می‌کنم قبل از خواب نفس عمیق بکش. من اینجام.", language="fa", created_at=now - timedelta(days=2)))
    for i in range(12):
        db.add(models.Memory(user_id=u.id, user_message=f"پیام شماره {i} امروز", sedi_response="باشه عزیزم", language="fa", created_at=now - timedelta(minutes=60 - i)))
    db.commit()
    hint = cc.build_continuity_hint(db, u.id, "fa")
    assert "رویداد_مهم_اخیر" in hint and "کارش" in hint
    assert "پیشنهادهای_قبلی_صدی" in hint and "نفس عمیق" in hint
    assert "[RECENT_LIFE_EVENT]" in cc.build_continuity_hint(db, u.id, "en")


def test_continuity_hint_is_empty_without_consent_or_data(db):
    u = _user(db, "+17770018005", tz="Asia/Tehran")
    assert cc.build_continuity_hint(db, u.id, "fa") == ""
    assert cc.build_continuity_hint(object(), 1, "fa") == ""  # fail-open
