"""D-130 (Javad's phone test 2026-10-28): Sedi asks «کِی یادت بندازم؟» and the user answers «میخوام تست کنم حدود ۵ دقیقه دیگه».
The answer has no reminder word, so it used to become a general question and the LLM refused («نمی‌تونم اعلان بفرستم»).
It is now the reminder.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app import models
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.intelligence.reminder_event_readiness import (
    _clarification,
    answer_as_reminder_request,
    is_reminder_clarification,
    parse_reminder_event_draft,
)
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _user

NOW = datetime(2026, 10, 27, 16, 0, tzinfo=timezone.utc)
FA_QUESTION = "کِی یادت بندازم؟ روز و ساعتش رو بگو، مثلاً «فردا ساعت ۱۰ صبح»."


class _Ctx:  # the orchestrator only reads ctx.locale.timezone here
    class locale:  # noqa: N801
        timezone = "Asia/Tehran"


def test_sedis_own_questions_are_recognised_in_every_language():
    for template in ("tpl.reminder.datetime.v1", "tpl.reminder.past.v1", "tpl.reminder.title.v1"):
        for lang in ("fa", "ar", "en"):
            text = _clarification(question_id="q", target_key="k", template_id=template, language=lang).localized_message
            assert is_reminder_clarification(text), (template, lang)
    assert is_reminder_clarification(FA_QUESTION)
    assert not is_reminder_clarification("سلام جواد جان")
    assert not is_reminder_clarification(None)


def test_the_answer_becomes_a_full_request_with_a_clean_title():
    req = answer_as_reminder_request("میخوام تست کنم حدود ۵ دقیقه دیگه", "fa")
    assert req == "یادم بنداز میخوام تست کنم حدود ۵ دقیقه دیگه"
    draft, missing = parse_reminder_event_draft(message=req, timezone_name="Asia/Tehran", now_utc=NOW, language="fa")
    assert missing is None and draft is not None
    assert draft.title == "تست" and draft.relative
    assert draft.starts_at_local == datetime(2026, 10, 27, 19, 35)  # 16:00 UTC = 19:30 Tehran + 5 min
    assert answer_as_reminder_request("in 5 minutes", "en") == "remind me in 5 minutes"


def _turn(db, user, *, response, minutes_ago=2, text="خوب صدی میخوام یه نوتیف پیگیری ارسال کنی"):
    db.add(
        models.Memory(
            user_id=user.id,
            user_message=text,
            sedi_response=response,
            language="fa",
            created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
        )
    )
    db.commit()


def _orch(db):
    return IntelligenceOrchestrator(db=db)


def test_answer_after_sedis_question_continues_the_reminder(db):
    u = _user(db, "+17770051001", tz="Asia/Tehran")
    _turn(db, u, response=FA_QUESTION)
    out = _orch(db)._continue_reminder_clarification(_Ctx, u.id, "میخوام تست کنم حدود ۵ دقیقه دیگه", "fa")
    assert out == "یادم بنداز میخوام تست کنم حدود ۵ دقیقه دیگه"


def test_nothing_changes_without_sedis_question_or_when_old_or_not_a_time(db):
    orch = _orch(db)
    u = _user(db, "+17770051002", tz="Asia/Tehran")
    msg = "میخوام تست کنم حدود ۵ دقیقه دیگه"
    assert orch._continue_reminder_clarification(_Ctx, u.id, msg, "fa") == msg  # no previous turn
    _turn(db, u, response="سلام جواد جان! امروز حالت چطوره؟")
    assert orch._continue_reminder_clarification(_Ctx, u.id, msg, "fa") == msg  # previous turn was not a question

    v = _user(db, "+17770051003", tz="Asia/Tehran")
    _turn(db, v, response=FA_QUESTION, minutes_ago=45)
    assert orch._continue_reminder_clarification(_Ctx, v.id, msg, "fa") == msg  # too old

    w = _user(db, "+17770051004", tz="Asia/Tehran")
    _turn(db, w, response=FA_QUESTION)
    assert orch._continue_reminder_clarification(_Ctx, w.id, "باشه ممنون", "fa") == "باشه ممنون"  # not a time
    assert orch._continue_reminder_clarification(_Ctx, w.id, "", "fa") == ""


def test_the_continuation_is_fail_open(db):
    orch = IntelligenceOrchestrator(db=None)
    assert orch._continue_reminder_clarification(_Ctx, 1, "۵ دقیقه دیگه", "fa") == "۵ دقیقه دیگه"
