"""P9: the app is opened again on the same day -> Sedi compresses today's earlier chats and invites the user to continue,
hear something new, or name their own topic (the same flow new days already have)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytz

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.services import a3_session_open as so
from backend.app.services.i7 import same_day_recap as sdr
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

TEHRAN = pytz.timezone("Asia/Tehran")


def _auth(uid):
    return {"Authorization": f"Bearer {create_access_token({'user_id': uid})}"}


def _fa_user(db, phone):
    u = _user(db, phone, tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = "fa"
    u.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=5)
    db.commit()
    _seed_consent(db, u.id)
    return u


def _earlier_today(db, uid, texts, *, reply="باشه"):
    """Turns spread over the elapsed part of the user's local day, the last one at least 5 minutes ago."""
    now = datetime.now(timezone.utc)
    midnight = TEHRAN.localize(datetime.combine(now.astimezone(TEHRAN).date(), datetime.min.time())).astimezone(timezone.utc)
    if now - midnight < timedelta(minutes=30):
        pytest.skip("too close to local midnight for a same-day fixture")
    span = (now - midnight) - timedelta(minutes=6)
    for i, text in enumerate(texts):
        at = midnight + span * (i + 1) / (len(texts) + 1)
        db.add(models.Memory(
            user_id=uid, user_message=text, sedi_response=reply, language="fa",
            created_at=at.replace(tzinfo=None), retain_until=at + timedelta(days=30),
        ))
    db.commit()


def test_returning_the_same_day_gets_a_recap_opener_with_three_ways_forward(db):
    u = _fa_user(db, "+17770051001")
    _earlier_today(db, u.id, ["میخوام یه رژیم غذایی برام بچینی", "این چند شب خوابم خوب نیست", "باشه"])
    text = so.maybe_proactive_opener(db, u)
    assert text and text.startswith("سلام جواد جان!")
    assert "امروز قبلاً درباره‌ی" in text and "برنامه‌ی غذایی و تغذیه‌ات" in text and "خوابت" in text
    assert "همون رو ادامه بدیم" in text and "پیشنهاد تازه" in text and "تو ذهنته" in text
    assert "رژیم غذایی برام" not in text and "خوش برگشتی" not in text and "سدی" not in text  # never the user's words


def test_an_unanswered_question_is_mentioned(db):
    u = _fa_user(db, "+17770051002")
    _earlier_today(db, u.id, ["میخوام برنامه ورزشی داشته باشم"], reply="چند روز در هفته می‌تونی ورزش کنی؟")
    assert "یه سؤال بی‌جواب مونده بود" in so.maybe_proactive_opener(db, u)


def test_a_crash_restart_right_after_a_message_is_not_a_return(db):
    u = _fa_user(db, "+17770051003")
    db.add(models.Memory(
        user_id=u.id, user_message="میخوام برنامه غذایی بدی", sedi_response="باشه", language="fa",
        created_at=datetime.utcnow() - timedelta(seconds=40), retain_until=datetime.now(timezone.utc) + timedelta(days=30),
    ))
    db.commit()
    assert so.maybe_proactive_opener(db, u) is None


def test_without_chats_today_the_old_behaviour_is_unchanged(db):
    u = _fa_user(db, "+17770051004")
    old = datetime.utcnow() - timedelta(days=1)
    db.add(models.Memory(user_id=u.id, user_message="میخوام یه رژیم غذایی برام بچینی", sedi_response="ok", language="fa", created_at=old,
                         retain_until=datetime.now(timezone.utc) + timedelta(days=20)))
    db.commit()
    text = so.maybe_proactive_opener(db, u)
    assert "آخرین بار درباره‌ی" in text and "امروز قبلاً" not in text


def test_no_memory_consent_means_no_recap(db):
    u = _user(db, "+17770051005", tz="Asia/Tehran")
    u.sedi_intro_completed_at = datetime.now(timezone.utc) - timedelta(days=5)
    db.commit()
    _earlier_today(db, u.id, ["میخوام یه رژیم غذایی برام بچینی"])
    assert sdr.build_same_day_recap(db, u.id, "fa") is None


def test_only_the_users_own_chats_are_recapped(db):
    u = _fa_user(db, "+17770051006")
    other = _fa_user(db, "+17770051007")
    _earlier_today(db, other.id, ["میخوام یه رژیم غذایی برام بچینی"])
    assert sdr.build_same_day_recap(db, u.id, "fa") is None


@pytest.mark.parametrize("lang,needle", [("en", "Earlier today we talked about"), ("ar", "تحدثنا اليوم قبل قليل عن")])
def test_other_languages(db, lang, needle):
    recap = {"topics": ["your sleep", "your family"], "count": 2, "open_question": False}
    text = sdr.same_day_opener(lang, "Hi!", recap)
    assert needle in text and text.startswith("Hi!")


def test_the_chat_model_gets_todays_topics_for_a_later_continue(db):
    from backend.app.services.intelligence.care_continuity import build_continuity_hint

    u = _fa_user(db, "+17770051008")
    assert sdr.today_so_far_hint(db, u.id, "fa") == ""
    _earlier_today(db, u.id, ["میخوام یه رژیم غذایی برام بچینی"])
    hint = sdr.today_so_far_hint(db, u.id, "fa")
    assert hint.startswith("[امروز_تا_اینجا]") and "برنامه‌ی غذایی و تغذیه‌ات" in hint and "دوباره خلاصه نکن" in hint
    assert "[امروز_تا_اینجا]" in build_continuity_hint(db, u.id, "fa")
    assert sdr.today_so_far_hint(db, u.id, "en").startswith("[TODAY_SO_FAR]")


def test_session_open_endpoint_returns_the_recap(client, db):
    u = _fa_user(db, "+17770051009")
    _earlier_today(db, u.id, ["میخوام یه رژیم غذایی برام بچینی"])
    r = client.post("/interact/session/open", headers=_auth(u.id))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "امروز قبلاً درباره‌ی" in (body.get("proactive_opener") or "")
    assert body["message"] == body["proactive_opener"]
