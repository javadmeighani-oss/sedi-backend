"""D-103 (Javad's phone test 2026-10-27).

1. «الان یک نوتیف پیگیری برای من ارسال کن» was answered by the LLM («نمی‌تونم نوتیفیکیشن بفرستم») because no intent rule
   matched; it is a reminder/notification action (R-026) and must reach the reminder path.
2. The opener said «آخرین بار درباره‌ی من مادرم این بیماری را داشت. میخواهم بیشتر…»: with no classifiable recent turn it fell
   back to an OLD stored «interest» sentence. The recap must be about the LAST chat and never echo a stored story.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app import models
from backend.app.services.i7 import conversation_recap as cr
from backend.app.services.intelligence.intent_registry import resolve_intent
from backend.app.services.intelligence.reminder_event_readiness import parse_reminder_event_draft
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user


@pytest.mark.parametrize(
    "message, language",
    [
        ("الان یک نوتیف پیگیری برای من ارسال کن", "fa"),
        ("الان یه نوتیف پیگیری برای من ارسال کن", "fa"),
        ("یه نوتیف بفرست برام", "fa"),
        ("send me a notification now", "en"),
        ("ارسل لي اشعار الان", "ar"),
    ],
)
def test_send_me_a_notification_is_a_reminder_action(message, language):
    assert resolve_intent(message=message, language=language).intent_id.value == "reminder"


@pytest.mark.parametrize(
    "message, language",
    [
        ("چرا نوتیف نمیاد؟", "fa"),
        ("نوتیف‌ها چطور کار می‌کنن", "fa"),
        ("why do notifications arrive late", "en"),
    ],
)
def test_questions_about_notifications_stay_general(message, language):
    assert resolve_intent(message=message, language=language).intent_id.value == "general"


def test_notification_now_request_becomes_a_two_minute_followup_reminder():
    now = datetime(2026, 10, 27, 13, 0, tzinfo=timezone.utc)
    draft, missing = parse_reminder_event_draft(
        message="الان یک نوتیف پیگیری برای من ارسال کن", timezone_name="Asia/Tehran", now_utc=now, language="fa"
    )
    assert missing is None and draft is not None
    assert draft.title == "پیگیری" and draft.relative
    assert draft.starts_at_local == datetime(2026, 10, 27, 16, 32)  # 16:30 Tehran + the next scheduler tick


def test_stored_story_is_never_a_topic():
    story = "من مادرم این بیماری را داشت. میخواهم بیشتر در مورد دلایل ابتلا به این بیماری توضیح دهی"
    assert cr._looks_like_story(story)
    assert cr._looks_like_story("")
    assert not cr._looks_like_story("شنا")
    assert not cr._looks_like_story("کوه‌نوردی و موسیقی")


def test_recap_names_reminders_and_tone_chats():
    assert cr.classify_turn("الان یک نوتیف پیگیری برای من ارسال کن") == "reminders"
    assert cr.classify_turn("باید لحن محکم‌ترین استفاده کنم") == "tone"
    assert cr.topic_phrase_from_text("الان یک نوتیف پیگیری برای من ارسال کن", "fa") == "یادآورها و اعلان‌هات"
    assert cr.topic_phrase_from_text("send me a reminder", "en", privacy="lock_screen") == "your reminders and notifications"


def _story_fact(monkeypatch, story):
    row = SimpleNamespace(domain="preferences", key="interests", value_json=story)
    monkeypatch.setattr(
        "backend.app.services.i6.memory_writes.list_facts_readonly_or_empty", lambda db, uid: [row]
    )
    monkeypatch.setattr(
        "backend.app.services.memory.memory_contract.render_stated_value", lambda v: v
    )


def test_recent_chat_without_a_nameable_topic_does_not_fall_back_to_an_old_story(db, monkeypatch):
    u = _user(db, "+17770010301", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    _story_fact(monkeypatch, "من مادرم این بیماری را داشت. میخواهم بیشتر در مورد دلایل ابتلا توضیح دهی")
    now = datetime.utcnow()
    db.add(
        models.Memory(
            user_id=u.id,
            user_message="صدی چطوری امروز حالت خوبه",
            sedi_response="ok",
            language="fa",
            created_at=now - timedelta(minutes=5),
        )
    )
    db.commit()
    assert cr.recap_topic(db, u.id, "fa") is None  # generic warm opener, not the stale story


def test_no_recent_turn_and_only_a_story_in_memory_gives_no_topic(db, monkeypatch):
    u = _user(db, "+17770010302", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    _story_fact(monkeypatch, "من مادرم این بیماری را داشت. میخواهم بیشتر در مورد دلایل ابتلا توضیح دهی")
    assert cr.recap_topic(db, u.id, "fa") is None


def test_no_recent_turn_a_clean_interest_label_is_still_remembered(db, monkeypatch):
    u = _user(db, "+17770010303", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    _story_fact(monkeypatch, "کوه‌نوردی")
    assert cr.recap_topic(db, u.id, "fa") == "کوه‌نوردی"
