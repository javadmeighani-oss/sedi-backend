"""BE-C (Javad 2026-11-09): «ساعت ۵» can be 05:00 or 17:00 - Sedi ASKS morning/evening instead of guessing (fa / ar / en)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app import sedi_copy
from backend.app.services.intelligence import reminder_event_readiness as rer
from backend.app.services.intelligence.reminder_event_readiness import (
    ambiguous_period_hour,
    is_period_clarification,
    is_reminder_clarification,
    parse_reminder_event_draft,
    period_answer_as_request,
)

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)  # 15:30 in Tehran
TZ = "Asia/Tehran"


def _parse(message, lang=None):
    return parse_reminder_event_draft(message=message, timezone_name=TZ, now_utc=NOW, language=lang)


AMBIGUOUS = [
    ("fa", "فردا ساعت ۵ یادم بنداز جلسه دارم", 5),
    ("fa", "فردا ساعت 5 یادآوری کن", 5),
    ("fa", "امروز ساعت ۸ نوتیف بده", 8),
    ("fa", "فردا ساعت ۵:۳۰ یادم بنداز", 5),
    ("fa", "فردا ساعت ۱۲ یادم بنداز", 12),
    ("fa", "هر روز ساعت ۶ یادم بنداز قرص بخورم", 6),
    ("ar", "ذكرني غدا الساعة 5 بموعد الطبيب", 5),
    ("ar", "ذكرني غدا الساعة 9 بالدواء", 9),
    ("en", "remind me tomorrow at 5 to call the doctor", 5),
    ("en", "remind me tomorrow at 5:30 about the meeting", 5),
    ("en", "remind me at 11 to take my pills", 11),
]


@pytest.mark.parametrize("lang,message,hour", AMBIGUOUS)
def test_a_bare_12_hour_clock_is_asked_never_guessed(lang, message, hour):
    draft, missing = _parse(message, lang)
    assert (draft, missing) == (None, "period"), message
    assert ambiguous_period_hour(rer._normalize(message)) == hour


UNAMBIGUOUS = [
    ("fa", "فردا ساعت ۵ عصر یادم بنداز جلسه دارم", 17),
    ("fa", "فردا ساعت ۵ صبح یادم بنداز", 5),
    ("fa", "فردا ساعت ۵ بعدازظهر یادآوری کن", 17),
    ("fa", "فردا ساعت ۱۷ یادم بنداز", 17),
    ("fa", "فردا ساعت ۱۷:۳۰ یادم بنداز", 17),
    ("fa", "امشب ساعت ۹ یادم بنداز", 21),
    ("fa", "فردا ساعت ۱۲ ظهر یادم بنداز", 12),
    ("fa", "فردا ساعت ۱۴ یادآوری کن", 14),
    ("ar", "ذكرني غدا الساعة 5 مساء", 17),
    ("ar", "ذكرني غدا الساعة 5 صباحا", 5),
    ("ar", "ذكرني غدا الساعة 17", 17),
    ("en", "remind me tomorrow at 5 pm to call the doctor", 17),
    ("en", "remind me tomorrow at 5am", 5),
    ("en", "remind me tomorrow at 17:30", 17),
    ("en", "remind me tomorrow morning at 8", 8),
    ("en", "remind me tonight at 9", 21),
]


@pytest.mark.parametrize("lang,message,hour", UNAMBIGUOUS)
def test_clear_times_are_scheduled_without_a_question(lang, message, hour):
    draft, missing = _parse(message, lang)
    assert missing is None and draft is not None, (message, missing)
    assert draft.starts_at_local.hour == hour, message


def test_relative_times_and_other_missing_slots_are_untouched():
    d, miss = _parse("نیم ساعت دیگه یادم بنداز")
    assert miss is None and d.relative
    assert _parse("فردا یادم بنداز")[1] == "datetime"
    assert _parse("فردا ساعت ۱۰ صبح یادم بنداز")[1] is None


# ---- the question and the binding of the short answer ---------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_question_names_the_hour_and_is_recognised_as_a_reminder_question(lang):
    text = rer._clarification(question_id="q", target_key="k", template_id="tpl.reminder.period.v1", language=lang, hour=5).localized_message
    assert "5" in text and "{h}" not in text
    assert is_period_clarification(text) and is_reminder_clarification(text)


def test_a_normal_sedi_sentence_is_not_mistaken_for_the_period_question():
    assert not is_period_clarification("منظورت چیه؟ بیشتر توضیح بده")
    assert not is_period_clarification("Do you mean the doctor or the dentist?")


@pytest.mark.parametrize(
    "prior,answer,expected_hour",
    [
        ("فردا ساعت ۵ یادم بنداز جلسه دارم", "عصر", 17),
        ("فردا ساعت ۵ یادم بنداز جلسه دارم", "صبح", 5),
        ("remind me tomorrow at 5 to call the doctor", "evening", 17),
        ("remind me tomorrow at 5 to call the doctor", "morning", 5),
        ("ذكرني غدا الساعة 5 بموعد الطبيب", "مساء", 17),
    ],
)
def test_the_one_word_answer_completes_the_original_request(prior, answer, expected_hour):
    combined = period_answer_as_request(prior, answer)
    draft, missing = _parse(combined)
    assert missing is None and draft.starts_at_local.hour == expected_hour


def test_an_answer_without_a_period_word_is_not_bound():
    assert period_answer_as_request("فردا ساعت ۵ یادم بنداز", "نمی‌دونم") is None
    assert period_answer_as_request("", "عصر") is None


def test_the_orchestrator_binds_the_answer_before_the_old_clarification_path():
    import inspect

    from backend.app.services.intelligence import orchestrator

    src = inspect.getsource(orchestrator.IntelligenceOrchestrator._continue_reminder_clarification)
    assert src.index("is_period_clarification") < src.index("asked = is_reminder_clarification")


# ---- rollback switch ------------------------------------------------------------------------------------------------------------------
def test_the_env_switch_restores_the_old_heuristic(monkeypatch):
    monkeypatch.setenv(rer.ASK_PERIOD_ENV, "0")
    draft, missing = _parse("فردا ساعت ۵ یادم بنداز جلسه دارم", "fa")
    assert missing is None and draft.starts_at_local.hour == 17
    monkeypatch.setenv(rer.ASK_PERIOD_ENV, "1")
    assert _parse("فردا ساعت ۵ یادم بنداز جلسه دارم", "fa")[1] == "period"


def test_copy_catalog_has_the_three_language_pair():
    for key in ("reminder.clarify.period", "reminder.clarify_opening.period"):
        assert set(sedi_copy.by_lang(key)) >= {"fa", "ar", "en"}
