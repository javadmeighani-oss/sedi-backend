"""R-121 (Javad 2026-11-28): the welcome is drawn from the LATEST chats - what Sedi did there and what is still open - so the connection stays
continuous. Phone test D-544: after five cardiologists were introduced the opener said «امروز قبلاً درباره‌ی پیدا کردن پزشک مناسب برایت صحبت
کردیم. از کجا ادامه بدهیم؟». Also D-544: an introduction is always FIVE and a site's repeated expertise is shown once.

Real session (in-memory SQLite, the harness of test_r108_care_loop_e2e)."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import models, sedi_copy
from backend.app.services.i5 import site_readers as sr
from backend.app.services.i7 import governed_raw
from backend.app.services.i7 import last_conversation as lc
from backend.tests.test_r108_care_loop_e2e import _fixed_timezone, db, user  # noqa: F401  (real-session fixtures)

REQ = "برام یه متخصص قلب تو تهرانپارس تهران پیدا کن"
INTRO = "با بررسی سایت‌های معتبر، این پزشکان تأییدشده را برایت پیدا کردم:\n• دکتر الف — قلب\n\nتماس بگیر و مرا در جریان قرار بده."
STATE = {"v": 1, "entity": "SPECIALIST", "specialty": "قلب", "city": "تهران", "area": "تهرانپارس", "names": [f"دکتر {i}" for i in range(5)],
         "keys": [], "shown": 5}
NOW = datetime(2026, 11, 28, 9, 0, tzinfo=timezone.utc)


def _turn(db, user, message, reply, at):
    from backend.app.core.conversation.memory import ConversationMemory

    row = ConversationMemory(db).save_conversation(user.id, message, reply, "fa")
    assert row is not None
    row.created_at = at.replace(tzinfo=None)
    db.commit()
    return row


def _intro(db, user, at, state=STATE):
    _turn(db, user, REQ, INTRO, at)
    assert governed_raw.attach_provider_intro(db, user_id=user.id, sedi_response=INTRO, state=dict(state))
    db.commit()


# --- 1. doctors introduced -------------------------------------------------------------------------------------------------------------------------
def test_after_an_introduction_today_the_welcome_asks_which_one_he_called(db, user):
    _intro(db, user, NOW - timedelta(hours=2))
    out = lc.continuation(db, user.id, "fa", now=NOW)
    assert out == "امروز ۵ متخصص قلب در تهرانپارس تهران برایت معرفی کردم. با کدام‌شان تماس گرفتی یا وقت گرفتی؟"


def test_the_day_word_follows_the_users_calendar(db, user):
    _intro(db, user, NOW - timedelta(days=1))
    assert lc.continuation(db, user.id, "fa", now=NOW).startswith("دیروز ")
    assert lc.continuation(db, user.id, "fa", now=NOW + timedelta(days=3)).startswith("آخرین بار ")
    assert lc.continuation(db, user.id, "fa", now=NOW + timedelta(days=9)) is None  # a week later it is not «the last chat» any more


@pytest.mark.parametrize("lang,expected", [
    ("en", "Today I introduced 5 قلب doctors in تهرانپارس تهران to you. Which of them did you call or book?"),
    ("ar", "اليوم عرّفتك على ٥ أطباء قلب في تهرانپارس تهران. بأيّهم اتصلت أو حجزت موعداً؟"),
])
def test_every_language_gets_the_same_continuation(db, user, lang, expected):
    _intro(db, user, NOW - timedelta(hours=1))
    assert lc.continuation(db, user.id, lang, now=NOW) == expected


def test_a_physiotherapy_introduction_names_centres(db, user):
    _intro(db, user, NOW - timedelta(hours=1), {**STATE, "entity": "SPECIALTY_CENTER", "specialty": "فیزیوتراپی", "area": None, "city": "شیراز"})
    assert lc.continuation(db, user.id, "fa", now=NOW).startswith("امروز ۵ مرکز فیزیوتراپی در شیراز برایت معرفی کردم.")


def test_an_older_introduction_without_the_count_still_says_how_many(db, user):
    _intro(db, user, NOW - timedelta(hours=1), {k: v for k, v in STATE.items() if k != "shown"})
    assert "۵ متخصص قلب" in lc.continuation(db, user.id, "fa", now=NOW)


def test_a_newer_subject_after_the_introduction_is_the_last_chat(db, user):
    _intro(db, user, NOW - timedelta(hours=2))
    _turn(db, user, "دیشب خیلی بد خوابیدم و خسته‌ام", "خواب منظم کمک می‌کند.", NOW - timedelta(hours=1))
    out = lc.continuation(db, user.id, "fa", now=NOW)
    assert out is None or "معرفی کردم" not in out


@pytest.mark.parametrize("refusal", ["دیگه دکتر نمی‌خوام", "نیاز ندارم ممنون", "I don't need a doctor anymore", "لا أريد طبيباً"])
def test_p2_a_refusal_after_the_introduction_closes_it(db, user, refusal):
    """Codex P2 (PR 231): «I don't need a doctor any more» - reopening the app does not restart the declined request."""
    _intro(db, user, NOW - timedelta(hours=2))
    _turn(db, user, refusal, "باشه، هر وقت لازم شد بگو.", NOW - timedelta(hours=1))
    out = lc.continuation(db, user.id, "fa", now=NOW)
    assert out is None or "معرفی کردم" not in out


# --- 2. a reminder set in that chat ----------------------------------------------------------------------------------------------------------------
def test_a_reminder_set_in_the_last_chat_is_named_with_its_time(db, user):
    at = NOW - timedelta(hours=1)
    _turn(db, user, "فردا ساعت ۹ یادم بنداز قرص ویتامین D بخورم", "ثبت شد.", at)
    # starts_at is the event's LOCAL wall clock in its own timezone (as reminder_event_dispatch stores it)
    db.add(models.UserEvent(user_id=user.id, title="قرص ویتامین D", starts_at=datetime(2026, 11, 29, 9, 0), timezone="Asia/Tehran",
                            source="conversation", status="scheduled", created_at=at.replace(tzinfo=None)))
    db.commit()
    out = lc.continuation(db, user.id, "fa", now=NOW)
    assert out == "امروز یادآور «قرص ویتامین D» را برای فردا ساعت ۰۹:۰۰ ثبت کردم. برایش آماده‌ای؟"


def test_a_reminder_already_past_asks_if_it_was_done(db, user):
    at = NOW - timedelta(days=1)
    _turn(db, user, "امروز ساعت ۸ شب یادم بنداز ورزش کنم", "ثبت شد.", at)
    db.add(models.UserEvent(user_id=user.id, title="ورزش", starts_at=datetime(2026, 11, 27, 20, 0), timezone="Asia/Tehran", source="conversation",
                            status="scheduled", created_at=at.replace(tzinfo=None)))
    db.commit()
    assert lc.continuation(db, user.id, "fa", now=NOW) == "دیروز یادآور «ورزش» را برای دیروز ساعت ۲۰:۰۰ ثبت کردم. انجامش دادی؟"


def test_p2_a_local_reminder_time_is_not_read_as_utc(db, user):
    """Codex P2 (PR 231): 11:00 Tehran this morning has passed at 12:30 Tehran (read as UTC it would be 14:30, still ahead)."""
    at = NOW - timedelta(hours=4)
    _turn(db, user, "ساعت ۱۱ یادم بنداز به مادرم زنگ بزنم", "ثبت شد.", at)
    db.add(models.UserEvent(user_id=user.id, title="زنگ به مادرم", starts_at=datetime(2026, 11, 28, 11, 0), timezone="Asia/Tehran",
                            source="conversation", status="scheduled", created_at=at.replace(tzinfo=None)))
    db.commit()
    assert lc.continuation(db, user.id, "fa", now=NOW) == "امروز یادآور «زنگ به مادرم» را برای امروز ساعت ۱۱:۰۰ ثبت کردم. انجامش دادی؟"


def test_a_reminder_from_another_conversation_is_not_this_chat(db, user):
    _turn(db, user, "سلام، امروز حالم خوب است و کار زیادی دارم", "خوشحالم.", NOW - timedelta(hours=1))
    db.add(models.UserEvent(user_id=user.id, title="ورزش", starts_at=(NOW + timedelta(days=1)).replace(tzinfo=None), source="conversation",
                            status="scheduled", created_at=(NOW - timedelta(days=3)).replace(tzinfo=None)))
    db.commit()
    assert lc.continuation(db, user.id, "fa", now=NOW) is None


# --- 4. her unanswered question --------------------------------------------------------------------------------------------------------------------
def test_her_unanswered_question_is_asked_again(db, user):
    _turn(db, user, "این روزها خیلی استرس دارم", "استرس کاری فشار زیادی می‌آورد. بیشتر کدام ساعت‌های روز سراغت می‌آید؟", NOW - timedelta(days=1))
    assert lc.continuation(db, user.id, "fa", now=NOW) == "دیروز از تو پرسیده بودم: «بیشتر کدام ساعت‌های روز سراغت می‌آید؟»"


def test_nothing_concrete_keeps_the_topic_opener(db, user):
    _turn(db, user, "سلام، امروز حالم خوب است", "خوشحالم که حالت خوب است.", NOW - timedelta(hours=1))
    assert lc.continuation(db, user.id, "fa", now=NOW) is None


def test_without_memory_consent_nothing_is_read(db, user):
    from backend.app.services.i6 import consent_service

    _intro(db, user, NOW - timedelta(hours=1))
    consent_service.revoke_memory_consent(db, user.id)
    db.commit()
    assert lc.continuation(db, user.id, "fa", now=NOW) is None


# --- the opener paths use it ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("first_of_day,greeting", [(True, "صبح بخیر"), (False, "سلام")])
def test_the_welcome_paths_continue_the_last_chat(db, user, monkeypatch, first_of_day, greeting):
    from backend.app.services import a3_session_open as a3

    user.sedi_intro_completed_at = datetime.utcnow()
    db.commit()
    now = datetime.now(timezone.utc)
    _intro(db, user, now - timedelta(hours=7))
    monkeypatch.setattr(a3, "_first_open_of_local_day", lambda *a, **k: first_of_day)
    monkeypatch.setattr(a3, "_time_greeting", lambda *a, **k: "صبح بخیر سارا.")
    monkeypatch.setattr(a3, "_last_user_message_at", lambda *a, **k: now - timedelta(hours=7))
    import backend.app.services.i7.same_day_recap as sdr

    today = None if first_of_day else {"topics": ["پیدا کردن پزشک مناسب برایت"], "count": 3, "open_question": False}  # no chat yet on a new day
    monkeypatch.setattr(sdr, "build_same_day_recap", lambda *a, **k: today)
    out = a3.maybe_proactive_opener(db, user)
    assert out is not None and out.startswith(greeting) and "۵ متخصص قلب" in out and "با کدام‌شان تماس گرفتی" in out
    assert "از کجا ادامه بدهیم" not in out


# --- D-544: always five, expertise once ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,clean", [
    ("متخصص بیماریهای قلب و عروق, متخصص بیماریهای قلب و عروق", "متخصص بیماریهای قلب و عروق"),
    ("فلوشیپ اینترونشنال کاردیولوژی, متخصص بیماریهای قلب و عروق", "فلوشیپ اینترونشنال کاردیولوژی، متخصص بیماریهای قلب و عروق"),
    ("متخصص قلب", "متخصص قلب"),
    ("", ""),
])
def test_a_sites_expertise_list_is_shown_without_repeats(raw, clean):
    assert sr.unique_parts(raw) == clean
