"""R-062/R-065: the first app opening of every LOCAL day greets - for every user, language and time of day.

Phone test 2026-11-05: last message 23:17, app opened 08:09 (gap 8 h 52 m < the old 12 h cooldown) -> empty chat.
The rule is general (a matrix over parts of the day x languages x with/without a known topic x first/later opening),
not a patch for that one gap.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytz

from backend.app import models, sedi_copy
from backend.app.services import a3_session_open as so
from backend.app.services.auth_session_policy import SESSION_OPEN_EVENT_TYPE
from backend.app.services.gate4.interaction_event_service import create_interaction_event
from backend.app.services.intelligence.time_context import part_of_day
from backend.tests.test_p9_same_day_recap import _fa_user

TEHRAN = pytz.timezone("Asia/Tehran")
GOAL_QUESTION = "دقیقاً چه چیزی را می‌خواهی در سلامتت یا زندگی‌ات تغییر بدهی؟"


def _utc(local_naive: datetime) -> datetime:
    return TEHRAN.localize(local_naive).astimezone(timezone.utc)


def _fixed_now(monkeypatch, at_utc: datetime):
    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return at_utc if tz is None else at_utc.astimezone(tz)

    monkeypatch.setattr(so, "datetime", _Fixed)


def _open_event(db, uid, at_utc: datetime):
    ev = create_interaction_event(db, user_id=uid, event_type=SESSION_OPEN_EVENT_TYPE, source="system", metadata={"presence": True})
    ev.created_at = at_utc.replace(tzinfo=None)
    db.commit()


def _turn(db, uid, at_utc: datetime, text="این چند شب خوابم خوب نیست"):
    db.add(models.Memory(
        user_id=uid, user_message=text, sedi_response="باشه", language="fa",
        created_at=at_utc.replace(tzinfo=None), retain_until=datetime.now(timezone.utc) + timedelta(days=20),
    ))
    db.commit()


def test_overnight_gap_under_twelve_hours_still_greets_with_the_last_topic(db, monkeypatch):
    u = _fa_user(db, "+17770062001")
    today = datetime.now(timezone.utc).astimezone(TEHRAN).date()
    last = _utc(datetime.combine(today - timedelta(days=1), datetime.min.time()).replace(hour=23, minute=17))
    _turn(db, u.id, last)
    _open_event(db, u.id, last)
    _fixed_now(monkeypatch, _utc(datetime.combine(today, datetime.min.time()).replace(hour=8, minute=9)))
    text = so.maybe_proactive_opener(db, u)
    assert text and text.startswith("صبح بخیر جواد.")
    assert "آخرین بار درباره‌ی" in text and text.rstrip().endswith("؟")
    assert text.count("؟") == 1


def test_a_user_with_no_known_topic_is_asked_for_the_goal(db, monkeypatch):
    u = _fa_user(db, "+17770062002")
    today = datetime.now(timezone.utc).astimezone(TEHRAN).date()
    _fixed_now(monkeypatch, _utc(datetime.combine(today, datetime.min.time()).replace(hour=9, minute=0)))
    text = so.maybe_proactive_opener(db, u)
    assert text and text.startswith("صبح بخیر جواد.") and GOAL_QUESTION in text


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
@pytest.mark.parametrize("hour", [3, 8, 12, 15, 18, 22])
def test_the_greeting_follows_the_users_local_part_of_day(db, hour, lang):
    u = _fa_user(db, f"+1777006{3000 + hour}")
    u.preferred_language = lang
    db.commit()
    today = datetime.now(timezone.utc).astimezone(TEHRAN).date()
    now = _utc(datetime.combine(today, datetime.min.time()).replace(hour=hour, minute=30))
    name_part = so._name_part(u, lang)
    expected = sedi_copy.t("session.greet." + part_of_day(hour), lang, name_part=name_part)
    assert so._time_greeting(db, u.id, lang, name_part, now) == expected
    assert expected.strip().endswith(".")
    assert "جواد" in expected


def test_first_open_of_the_local_day_logic(db):
    u = _fa_user(db, "+17770062003")
    now = datetime.now(timezone.utc)
    assert so._first_open_of_local_day(db, u.id, now) is True  # never opened
    _open_event(db, u.id, now - timedelta(days=2))
    assert so._first_open_of_local_day(db, u.id, now) is True  # last opening on an earlier local day
    _open_event(db, u.id, now)
    assert so._first_open_of_local_day(db, u.id, now) is False  # already opened today


def test_a_second_opening_on_the_same_day_does_not_greet_again(db, monkeypatch):
    u = _fa_user(db, "+17770062004")
    today = datetime.now(timezone.utc).astimezone(TEHRAN).date()
    yesterday_night = _utc(datetime.combine(today - timedelta(days=1), datetime.min.time()).replace(hour=23, minute=17))
    _turn(db, u.id, yesterday_night)
    _open_event(db, u.id, _utc(datetime.combine(today, datetime.min.time()).replace(hour=8, minute=9)))
    _fixed_now(monkeypatch, _utc(datetime.combine(today, datetime.min.time()).replace(hour=10, minute=0)))
    assert so.maybe_proactive_opener(db, u) is None  # cooldown rule unchanged for later openings


def test_a_user_who_has_not_finished_the_intro_gets_no_new_day_greeting(db):
    u = _fa_user(db, "+17770062005")
    u.sedi_intro_completed_at = None
    db.commit()
    assert so.maybe_proactive_opener(db, u) is None


@pytest.mark.parametrize("lang,question", [("fa", "؟"), ("ar", "؟"), ("en", "?")])
def test_new_day_texts_are_one_question_in_every_language(lang, question):
    greet = sedi_copy.t("session.greet.morning", lang, name_part=" Sara")
    for key, kw in (("session.newday.topic", {"topic": "x y z"}), ("session.newday.goal", {})):
        text = sedi_copy.t(key, lang, greet=greet, **kw)
        assert text.count(question) == 1 and text.startswith(greet), (key, lang)
        assert "{" not in text
