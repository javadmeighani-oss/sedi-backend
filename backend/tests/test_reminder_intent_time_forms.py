"""Javad 2026-10-28 phone test: «یه نوتیف یادآوری تا ۲۱ و ۲۰ دقیقه برام ارسال کن» was not read as a reminder request
(the LLM answered «نمی‌تونم نوتیف واقعی بفرستم»). Two gaps: the intent phrases and the «۲۱ و ۲۰ دقیقه» (= 21:20) time form
without a day word."""
from __future__ import annotations

from datetime import datetime

import pytest

from backend.app.services.intelligence.intent_registry import IntentId, resolve_intent
from backend.app.services.intelligence.reminder_event_readiness import parse_reminder_event_draft

# 2026-10-28 17:47 UTC = 21:17 in Tehran (the minute of the phone test)
NOW = datetime(2026, 10, 28, 17, 47)
TZ = "Asia/Tehran"


def _parse(message: str):
    return parse_reminder_event_draft(message=message, timezone_name=TZ, now_utc=NOW, language="fa")


@pytest.mark.parametrize(
    "message",
    [
        "یه نوتیف یادآوری تا ۲۱ و ۲۰ دقیقه برام ارسال کن",
        "یک نوتیف یادآوری برای من بفرست",
        "برام یه اعلان یادآوری بفرست",
        "یادآوری بفرست ساعت ۹",
    ],
)
def test_notification_reminder_asks_are_reminder_intent(message):
    assert resolve_intent(message=message, language="fa").intent_id == IntentId.REMINDER


def test_the_phone_test_sentence_becomes_a_reminder_for_21_20_today():
    d, missing = _parse("یه نوتیف یادآوری تا ۲۱ و ۲۰ دقیقه برام ارسال کن")
    assert missing is None and d is not None
    assert d.starts_at_local == datetime(2026, 10, 28, 21, 20)
    assert d.reminder_offsets == (0,)
    assert d.title == "یادآوری"  # nothing else to say -> the localized default


@pytest.mark.parametrize(
    "message, when",
    [
        ("تا ساعت ۲۱ و ۲۰ دقیقه یادم بنداز", datetime(2026, 10, 28, 21, 20)),
        ("یادم بنداز ساعت ۲۱:۲۰ آب بخورم", datetime(2026, 10, 28, 21, 20)),
        ("ساعت ۲۱ و ۱۰ دقیقه یادآوری کن", datetime(2026, 10, 29, 21, 10)),  # 21:10 already passed -> tomorrow
        ("یادم بنداز ساعت ۱۰ صبح قرص بخورم", datetime(2026, 10, 29, 10, 0)),  # no day said, 10:00 passed -> tomorrow
    ],
)
def test_time_forms_without_a_day_word(message, when):
    d, missing = _parse(message)
    assert missing is None and d is not None, (message, missing)
    assert d.starts_at_local == when


def test_relative_forms_and_explicit_past_are_unchanged():
    d, _ = _parse("۲ ساعت و ۳۰ دقیقه دیگه یادم بنداز")  # relative: not read as 02:30
    assert d is None or d.starts_at_local.hour != 2
    assert _parse("امروز ساعت ۱۰ صبح یادم بنداز")[1] == "past"  # an explicit «today» that passed is still refused
    assert _parse("فردا یادم بنداز")[1] == "datetime"
    assert _parse("ساعت ۱۰ جلسه دارم")[1] == "datetime"  # a statement without reminder words does not guess a day
