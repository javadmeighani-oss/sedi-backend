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


# ---------------------------------------------------------------- 2026-10-28 21:35 phone test (second round)
def test_asking_sedi_to_send_a_notification_is_a_reminder_with_no_day_needed():
    # 21:35 in Tehran at NOW2 -> «ساعت ۲۱ و ۴۰ دقیقه» is today 21:40 and fires AT the time (not one hour before)
    now2 = datetime(2026, 10, 28, 18, 5)
    d, missing = parse_reminder_event_draft(
        message="میخوام برام یه نوتیف ارسال کنی در ساعت ۲۱ و ۴۰ دقیقه", timezone_name=TZ, now_utc=now2, language="fa"
    )
    assert missing is None and d is not None
    assert d.starts_at_local == datetime(2026, 10, 28, 21, 40)
    assert d.reminder_offsets == (0,)


def test_diacritics_do_not_hide_sedis_own_question():
    from backend.app.services.intelligence.reminder_event_readiness import is_reminder_clarification

    assert is_reminder_clarification("کِی یادت بندازم؟ روز و ساعتش رو بگو")
    assert is_reminder_clarification("کی یادت بندازم؟ روز و ساعتش رو بگو")  # the same text without the kasra
    assert not is_reminder_clarification("امروز چطور بود؟")


def test_persona_prompt_says_sedi_can_send_notifications():
    from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1

    assert "Never say you cannot send notifications" in PersonaPolicyV1.system_prompt("en")


def test_the_screenshot_conversation_is_continued_even_after_an_llm_turn(db):
    """T1 (no day) -> clarification; T2 «الان»; T3 «امشب ۲۱و ۳۷ دقیقه»; T4 «۲۱ و ۴۰ دقیقه بفرست» must all become reminders."""
    from datetime import timedelta

    from backend.app import models
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

    u = _user(db, "+17770071777", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    orch = IntelligenceOrchestrator.__new__(IntelligenceOrchestrator)
    orch._db = db
    orch._reminder_timezone = lambda ctx, user_id: "Asia/Tehran"

    def turn(msg: str, reply: str, ago_min: int):
        db.add(models.Memory(user_id=u.id, user_message=msg, sedi_response=reply, language="fa",
                             created_at=datetime.utcnow() - timedelta(minutes=ago_min)))
        db.commit()

    # nothing before: a short time answer alone is left alone
    assert orch._continue_reminder_clarification(None, u.id, "۲۱ و ۴۰ دقیقه بفرست", "fa") == "۲۱ و ۴۰ دقیقه بفرست"

    # T1 stays unfinished (no time) and Sedi's question lost its kasra on the way
    turn("میخوام برام یه نوتیف ارسال کنی", "کی یادت بندازم؟ روز و ساعتش رو بگو، مثلاً «فردا ساعت ۱۰ صبح».", 9)
    out = orch._continue_reminder_clarification(None, u.id, "الان", "fa")
    assert out == "یادم بنداز الان"

    # the next turns were answered by the LLM («نمی‌تونم ...») - the unfinished request is still the anchor
    turn("الان", "الان هم نمی‌تونم نوتیف واقعی روی گوشیت بفرستم.", 6)
    turn("امشب ۲۱و ۳۷ دقیقه", "آها، الان ۲۱:۳۷ شده و زمان ۲۱:۲۰ گذشته.", 3)
    assert orch._continue_reminder_clarification(None, u.id, "۲۱ و ۴۰ دقیقه بفرست", "fa") == "یادم بنداز ۲۱ و ۴۰ دقیقه بفرست"

    # a chat line that is not a time answer is never hijacked
    assert orch._continue_reminder_clarification(None, u.id, "ممنون، شب بخیر", "fa") == "ممنون، شب بخیر"
    # ...and a long message is never hijacked
    long_msg = "امشب خیلی خسته‌ام و ۲۱ و ۴۰ دقیقه هم دیرتر از چیزی بود که فکر می‌کردم شد"
    assert orch._continue_reminder_clarification(None, u.id, long_msg, "fa") == long_msg


def test_a_finished_reminder_does_not_swallow_later_chat(db):
    from datetime import timedelta

    from backend.app import models
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

    u = _user(db, "+17770071778", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    orch = IntelligenceOrchestrator.__new__(IntelligenceOrchestrator)
    orch._db = db
    orch._reminder_timezone = lambda ctx, user_id: "Asia/Tehran"
    db.add(models.Memory(user_id=u.id, user_message="فردا ساعت ۱۰ صبح یادم بنداز قرص بخورم",
                         sedi_response="باشه، فردا ساعت ۱۰ یادت میندازم.", language="fa",
                         created_at=datetime.utcnow() - timedelta(minutes=5)))
    db.commit()
    assert orch._continue_reminder_clarification(None, u.id, "۵ دقیقه دیگه میرم بیرون", "fa") == "۵ دقیقه دیگه میرم بیرون"
