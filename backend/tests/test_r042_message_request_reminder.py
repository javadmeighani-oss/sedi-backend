"""R-042 / R-103 (Javad's pilot test 2026-11-21): «میخواهم برای هر روز ساعت ۹ صبح به من پیام مصرف قرص بدی» is a DAILY reminder.

Pilot: Sedi treated it as a habit statement, asked «every day or every week?» although «هر روز» was said, then bound the user's complaint
«میگم ۹ صبح» (= I SAID 9 am) to that question and answered «tomorrow 09:00 I remind you: «میگم»». Two causes, both fixed:
  1. the habit-statement guard accepted only reminder WORDS, not the CONCEPT of asking Sedi to send a message (R-042);
  2. a reply that does not name daily/weekly/once was bound to the recurrence question, and a speech remark became the title.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.intelligence import reminder_event_readiness as r

TZ = "Asia/Tehran"


def _draft(message, lang="fa"):
    return r.parse_reminder_event_draft(message=message, timezone_name=TZ, language=lang)


# --- the exact pilot sentence and its neighbours ---------------------------------------------------------------------------------------------------
def test_the_pilot_sentence_is_a_daily_reminder_with_a_clean_title():
    draft, missing = _draft("میخواهم برای هر روز ساعت ۹ صبح به من پیام مصرف قرص بدی")
    assert missing is None and draft.recurrence_rule == "FREQ=DAILY" and draft.starts_at_local.strftime("%H:%M") == "09:00"
    assert draft.title == "مصرف قرص"  # the asking words are not the topic


@pytest.mark.parametrize(
    "message,lang,hour",
    [
        ("هر روز ساعت ۹ صبح بهم پیام بده قرصمو بخورم", "fa", "09:00"),
        ("هر روز ساعت ۷ صبح برام پیام بفرست ورزش کنم", "fa", "07:00"),
        ("هر شب ساعت ۱۰ شب به من پیام بدی که قرصم را بخورم", "fa", "22:00"),
        ("every day at 9 am send me a message to take my pill", "en", "09:00"),
        ("كل يوم الساعة 9 صباحا ارسل لي رسالة لاخذ الدواء", "ar", "09:00"),
    ],
)
def test_asking_sedi_for_a_message_at_a_time_every_day_is_a_reminder_in_any_wording(message, lang, hour):
    draft, missing = _draft(message, lang)
    assert missing is None and draft is not None and draft.recurrence_rule == "FREQ=DAILY" and draft.starts_at_local.strftime("%H:%M") == hour


@pytest.mark.parametrize(
    "message,lang",
    [
        ("هر شب ساعت ۱۱ می‌خوابم", "fa"),            # a habit statement
        ("من هر روز ساعت ۹ قرص می‌خورم", "fa"),
        ("I take my pill every day at 9", "en"),
        ("چرا هر روز ساعت ۹ پیام نمی‌دی", "fa"),      # a complaint about a message
    ],
)
def test_habit_statements_and_complaints_are_still_not_reminders(message, lang):
    draft, missing = _draft(message, lang)
    assert draft is None and missing == "recurrence"


# --- the answer to «every day or every week?» -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_recurrence_question_is_recognised_in_every_language(lang):
    assert r.is_recurrence_question(sedi_copy.t("reminder.clarify.recurrence", lang)) is True
    assert r.is_recurrence_question("یه جواب معمولی") is False and r.is_recurrence_question(None) is False


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("هر روز", True), ("هر هفته", True), ("روزانه", True), ("هفتگی", True), ("فقط یک بار", True), ("یه بار", True),
        ("daily", True), ("every week", True), ("just once", True), ("كل يوم", True), ("مرة واحدة", True),
        ("میگم ۹ صبح", False), ("9 am", False), ("باشه", False), ("چی میگی", False), ("", False),
    ],
)
def test_only_a_message_that_says_daily_weekly_or_once_answers_the_question(answer, expected):
    assert r.answer_names_recurrence(answer) is expected


def test_a_speech_remark_is_never_a_reminder_title():
    draft, missing = _draft(r.answer_as_reminder_request("میگم ۹ صبح", "fa"))
    assert missing is None and "میگم" not in draft.title  # the title falls back to the default, not «میگم»
    assert "گفتم" not in _draft("یادم بنداز فردا ساعت ۹ صبح گفتم")[0].title


def _orchestrator(rows):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows
    return IntelligenceOrchestrator(db=db, legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)


def _ctx():
    return SimpleNamespace(locale=SimpleNamespace(timezone=TZ))


def _asked_recurrence():
    return [SimpleNamespace(user_message="x", sedi_response=sedi_copy.t("reminder.clarify.recurrence", "fa"), created_at=datetime.utcnow() - timedelta(minutes=1))]


def _waiting_for_recurrence():
    """The earlier request («every 2 hours …») waits for daily/weekly; Sedi asked the recurrence question."""
    return [
        SimpleNamespace(user_message="هر ۲ ساعت یادم بنداز قرصمو بخورم", sedi_response=sedi_copy.t("reminder.clarify.recurrence", "fa"), created_at=datetime.utcnow() - timedelta(minutes=1)),
    ]


def test_the_orchestrator_does_not_bind_a_remark_to_the_recurrence_question():
    orch = _orchestrator(_waiting_for_recurrence())
    assert orch._continue_reminder_clarification(_ctx(), 1, "میگم ۹ صبح", "fa") == "میگم ۹ صبح"  # left to the normal conversation


def test_the_orchestrator_still_binds_a_real_recurrence_answer():
    orch = _orchestrator(_waiting_for_recurrence())
    out = orch._continue_reminder_clarification(_ctx(), 1, "هر روز ساعت ۹ صبح", "fa")
    assert out != "هر روز ساعت ۹ صبح" and "هر روز" in out  # phrased as a full reminder request


def test_the_pilot_conversation_end_to_end():
    """Javad's exact two turns: the first is already a complete daily reminder, so no recurrence question is asked and nothing is bound."""
    first = "میخواهم برای هر روز ساعت ۹ صبح به من پیام مصرف قرص بدی"
    draft, missing = _draft(first)
    assert missing is None and draft.recurrence_rule == "FREQ=DAILY"  # no «every day or every week?» question
    orch = _orchestrator([SimpleNamespace(user_message=first, sedi_response="باشه، ثبتش کردم", created_at=datetime.utcnow() - timedelta(minutes=1))])
    assert orch._continue_reminder_clarification(_ctx(), 1, "میگم ۹ صبح", "fa") == "میگم ۹ صبح"  # a remark is never turned into a reminder titled «میگم»


# --- Codex round 1 on PR 205 ------------------------------------------------------------------------------------------------------------------
def test_p2_a_message_request_fires_at_the_stated_time_not_an_hour_before():
    for message, hour in (("میخواهم برای هر روز ساعت ۹ صبح به من پیام مصرف قرص بدی", "09:00"), ("میخواهم برای هر روز ساعت ۹ صبح به من پیام ورزش بدی", "09:00")):
        draft, missing = _draft(message)
        assert missing is None and draft.reminder_offsets == (0,) and draft.starts_at_local.strftime("%H:%M") == hour  # not (60,) = 08:00
    draft, _ = _draft("every day at 9 am send me a message to take my pill", "en")
    assert draft.reminder_offsets == (0,)


@pytest.mark.parametrize("answer", ["هر دوشنبه ساعت ۹ صبح", "every Monday at 9am", "هر جمعه", "every Friday"])
def test_p2_weekday_based_answers_still_name_a_recurrence(answer):
    assert r.answer_names_recurrence(answer) is True


def test_p2_a_weekday_recurrence_answer_still_continues_the_waiting_request():
    orch = _orchestrator(_waiting_for_recurrence())
    out = orch._continue_reminder_clarification(_ctx(), 1, "هر دوشنبه ساعت ۹ صبح", "fa")
    assert out != "هر دوشنبه ساعت ۹ صبح" and "دوشنبه" in out
