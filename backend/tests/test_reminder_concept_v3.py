"""R-026 v3 (Javad 2026-10-29): Sedi understands the CONCEPT "reach me at that day / time", not a list of keywords.

The real chat: «میخوام فردا ساعت ۱۰ بهم نوتیف بدی برای صحبت در مورد شنبه» was answered by the model with "I cannot send
notifications"; it must become a reminder for 10:00 tomorrow titled «صحبت درباره‌ی شنبه» (Saturday is the topic, not the date)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.services.intelligence.contracts import IntentId
from backend.app.services.intelligence.intent_registry import resolve_intent
from backend.app.services.intelligence.reminder_event_readiness import looks_like_notify_request, parse_reminder_event_draft

NOW = datetime(2026, 10, 29, 20, 0, tzinfo=timezone.utc)  # 23:30 in Tehran


def _draft(message: str, lang: str):
    return parse_reminder_event_draft(message=message, timezone_name="Asia/Tehran", now_utc=NOW, language=lang)


def test_the_real_chat_sentence_is_a_reminder_for_ten_tomorrow_about_saturday():
    message = "میخوام فردا ساعت ۱۰ بهم نوتیف بدی برای صحبت در مورد شنبه"
    assert resolve_intent(message=message, language="fa").intent_id is IntentId.REMINDER
    draft, missing = _draft(message, "fa")
    assert missing is None
    assert (draft.starts_at_local.month, draft.starts_at_local.day, draft.starts_at_local.hour) == (10, 30, 10)
    assert draft.title == "صحبت درباره‌ی شنبه"
    assert draft.reminder_offsets == (0,) or draft.reminder_offsets  # the reminder itself is on


@pytest.mark.parametrize(
    "lang, message",
    [
        ("fa", "فردا ساعت ۱۰ بهم نوتیف بده که درباره‌ی شنبه حرف بزنیم"),
        ("fa", "فردا ساعت ۱۰ صبح بهم خبر بده"),
        ("fa", "پس‌فردا ساعت ۸ شب یه پیام بهم بده قرصمو بخورم"),
        ("fa", "فردا ساعت ۱۰ صدام کن"),
        ("fa", "شنبه ساعت ۹ بهم زنگ بزن"),
        ("fa", "ساعت ۱۰ برای صحبت درباره شنبه بهم خبر بده"),
        ("en", "can you ping me tomorrow at 10 to talk about Saturday"),
        ("en", "text me tomorrow at 9am about my medication"),
        ("en", "let me know at 6pm"),
        ("ar", "أريد أن ترسل لي إشعاراً غداً الساعة 10 للحديث عن السبت"),
        ("ar", "نبهني غداً الساعة 9 عن الدواء"),
    ],
)
def test_different_words_same_concept_all_become_reminders(lang, message):
    assert looks_like_notify_request(message, lang) is True
    assert resolve_intent(message=message, language=lang).intent_id is IntentId.REMINDER
    draft, missing = _draft(message, lang)
    assert missing is None and draft is not None, message


@pytest.mark.parametrize(
    "lang, message",
    [
        ("fa", "دیروز ساعت ۱۰ بهم نوتیف دادی"),  # the past
        ("fa", "چرا نوتیف نمیاد؟"),  # a complaint, no time
        ("fa", "شنبه چه روزیه؟"),
        ("fa", "ساعت ۱۰ فردا جلسه دارم"),  # an appointment, handled by its own rule, not by the notify concept
        ("en", "what time is it tomorrow at 10"),
        ("ar", "ما هو الطقس غداً"),
    ],
)
def test_other_sentences_are_not_stolen_by_the_concept(lang, message):
    assert looks_like_notify_request(message, lang) is False


def test_a_topic_word_is_never_the_date():
    # no day said: «شنبه» is the topic, so the clock decides (the next 10:00), not "next Saturday"
    draft, missing = _draft("ساعت ۱۰ برای صحبت درباره شنبه بهم خبر بده", "fa")
    assert missing is None
    assert (draft.starts_at_local.day, draft.starts_at_local.hour) == (30, 10)
    assert draft.title == "صحبت درباره‌ی شنبه"
    en, _ = _draft("ping me tomorrow at 10 to talk about Saturday", "en")
    assert en.title == "talk about Saturday" and en.starts_at_local.day == 30


def test_a_plain_call_has_a_default_title_not_a_leftover_verb():
    draft, missing = _draft("شنبه ساعت ۹ بهم زنگ بزن", "fa")
    assert missing is None and draft.title.strip() and draft.title.strip() != "بزن"
    assert draft.starts_at_local.weekday() == 5  # Saturday


def test_existing_keyword_reminders_are_unchanged():
    draft, missing = _draft("فردا ساعت ۱۰ صبح یادم بنداز آزمایش خون بدم", "fa")
    assert missing is None and draft.event_type == "lab_test"
    assert resolve_intent(message="یادم بنداز فردا ساعت ۹ دارو بخورم", language="fa").intent_id is IntentId.REMINDER
