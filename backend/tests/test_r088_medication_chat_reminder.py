"""R-088 / R-091 (D-382..D-384) package A1: pill reminder in chat -> medication owner, asks WHICH pill.

Offline and DB-free: the owner service is stubbed; detection / name / answer parsing run for real.
Matrix: phrasing x language x named / unnamed.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services.medication_care import chat_reminder as mc


@pytest.mark.parametrize(
    "text",
    [
        "هر روز ساعت ۲ بعدازظهر یادم بنداز قرص بخورم",
        "هر شب ساعت ۹ یادم بنداز ویتامین D بخورم",
        "یه یادآور بذار برای داروی فشارم هر روز ساعت ۸",
        "remind me every day at 8 to take my pill",
        "remind me daily to take my medication at 9pm",
        "كل يوم الساعة 8 ذكّرني بدوائي",
    ],
)
def test_pill_reminders_are_detected(text):
    assert mc.is_medication_text(text)


@pytest.mark.parametrize(
    "text",
    [
        "یادم بنداز فردا برم داروخانه",
        "یادم بنداز فردا ساعت ۱۰ جلسه دارم",
        "remind me to go to the pharmacy tomorrow",
        "هر روز ساعت ۶ ورزش یادم بنداز",
    ],
)
def test_other_reminders_are_not_medication(text):
    assert not mc.is_medication_text(text)


@pytest.mark.parametrize(
    "text, name",
    [
        ("هر روز ساعت ۸ قرص متفورمین بخورم", "متفورمین"),
        ("هر روز ساعت ۲ قرص بخورم", None),  # the user's own pill message: no name -> ask which pill
        ("هر روز ساعت ۸ داروی فشارم بخورم", None),  # «داروی X» names a condition, not a medicine: ask which pill
        ("remind me daily to take Levothyroxine pill", "Levothyroxine"),
        ("remind me daily to take my vitamin", None),
        ("remind me daily to take my pill", None),
        ("هر روز ساعت ۸ کپسول امگا۳ بخورم", "امگا۳"),
    ],
)
def test_pill_name_extraction(text, name):
    assert mc.extract_pill_name(text) == name


def test_weekly_days_map_to_monday_zero():
    assert mc._days_of_week("FREQ=WEEKLY;BYDAY=MO,TH") == "0,3"
    assert mc._days_of_week("FREQ=DAILY") is None
    assert mc._is_recurring("FREQ=DAILY") and mc._is_recurring("FREQ=WEEKLY;BYDAY=FR")
    assert not mc._is_recurring(None) and not mc._is_recurring("")


class _Draft(SimpleNamespace):
    pass


def _draft(rule="FREQ=DAILY"):
    return _Draft(starts_at_local=datetime(2026, 11, 18, 14, 0), recurrence_rule=rule)


def _stub_owner(monkeypatch, record):
    from backend.app.services import user_medication_service as svc

    def fake_create(db, user_id, body):
        record.append(body)
        return {"id": 7}

    monkeypatch.setattr(svc, "create_user_medication", fake_create)


def test_recurring_pill_reminder_goes_to_the_medication_owner(monkeypatch):
    seen = []
    _stub_owner(monkeypatch, seen)
    out = mc.create_from_draft(
        None, user_id=1, message="هر روز ساعت ۲ بعدازظهر یادم بنداز قرص بخورم", draft=_draft(), language="fa", timezone_name="Asia/Tehran"
    )
    assert out and out["created"] and out["kind"] == "medication" and out["named"] is False and out["time"] == "14:00"
    assert seen[0].name == mc.provisional_name("fa") and seen[0].reminder_times == ["14:00"]


def test_named_pill_keeps_the_typed_name(monkeypatch):
    seen = []
    _stub_owner(monkeypatch, seen)
    out = mc.create_from_draft(
        None, user_id=1, message="هر روز ساعت ۸ قرص متفورمین بخورم", draft=_draft(), language="fa", timezone_name=None
    )
    assert out["named"] is True and seen[0].name == "متفورمین"


def test_one_off_and_non_medication_reminders_stay_on_the_user_event_path(monkeypatch):
    seen = []
    _stub_owner(monkeypatch, seen)
    assert mc.create_from_draft(None, user_id=1, message="فردا ساعت ۲ قرص بخورم", draft=_draft(None), language="fa", timezone_name=None) is None
    assert mc.create_from_draft(None, user_id=1, message="هر روز ساعت ۶ ورزش یادم بنداز", draft=_draft(), language="fa", timezone_name=None) is None
    assert seen == []


def test_kill_switch_and_owner_failure_fall_back(monkeypatch):
    seen = []
    _stub_owner(monkeypatch, seen)
    monkeypatch.setenv(mc.DISABLED_ENV, "1")
    assert mc.create_from_draft(None, user_id=1, message="هر روز قرص بخورم", draft=_draft(), language="fa", timezone_name=None) is None
    monkeypatch.delenv(mc.DISABLED_ENV)
    from backend.app.services import user_medication_service as svc

    def boom(db, user_id, body):
        raise RuntimeError("db down")

    monkeypatch.setattr(svc, "create_user_medication", boom)
    db = SimpleNamespace(rollback=lambda: None)
    assert mc.create_from_draft(db, user_id=1, message="هر روز ساعت ۲ قرص بخورم", draft=_draft(), language="fa", timezone_name=None) is None


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_confirmation_asks_one_question_about_the_exact_name_and_is_recognised_later(lang):
    unnamed = mc.confirmation({"named": False}, lang, "X-WHEN")
    named = mc.confirmation({"named": True, "name": "Zed"}, lang, "X-WHEN")
    for text in (unnamed, named):
        assert "X-WHEN" in text
        assert text.count("?") + text.count("؟") == 1  # ONE question (R-020/R-067)
        assert mc._asked_for_pill(text, lang)  # the next-turn binding recognises it
        assert "photo" in text.lower() or "عکس" in text or "صورة" in text  # spelling / photo of the box (R-088 am.3)
    assert "Zed" in named and "{" not in named and "{" not in unnamed


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_unrelated_reply_is_not_treated_as_a_pill_answer(lang):
    assert not mc._asked_for_pill("سلام، امروز چطوری؟", lang)
    assert not mc._asked_for_pill(None, lang)


@pytest.mark.parametrize(
    "reply, expected",
    [
        ("لووتیروکسین", "لووتیروکسین"),
        ("اسمش متفورمین هست", "متفورمین"),
        ("قرص آتورواستاتین", "آتورواستاتین"),
        ("Levothyroxine", "levothyroxine"),
        ("بله", None),
        ("نه", None),
        ("یک جمله‌ی خیلی بلند که اصلاً اسم قرص نیست و درباره‌ی چیز دیگری است", None),
    ],
)
def test_candidate_name_from_a_short_reply(reply, expected):
    got = mc._candidate_name(reply)
    assert (got.lower() if got else None) == expected


def test_catalog_texts_have_the_same_placeholders_and_no_slang():
    for key in ("medication.chat.bound", "medication.chat.kept", "medication.chat.already_tracked"):
        for lang in ("fa", "ar", "en"):
            assert "{name}" in sedi_copy.t(key, lang)
    for lang in ("fa", "ar", "en"):
        assert sedi_copy.t("medication.chat.provisional_name", lang)
