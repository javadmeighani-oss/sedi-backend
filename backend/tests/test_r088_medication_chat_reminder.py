"""R-088 / R-091 (D-382..D-387) package A1 v2: pill reminder in chat = care interview BEFORE any time is set.

Offline and DB-free: the owner write (_create) and the conversation (_recent_turns) are stubbed; detection, name parsing, the
stage markers and the interview state machine run for real. Matrix: phrasing x language x stage.
"""
from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services.medication_care import chat_reminder as mc

TZ = "Asia/Tehran"
REQUEST = "هر روز ساعت ۲ بعدازظهر یادم بنداز قرص بخورم"


@pytest.fixture(autouse=True)
def _no_real_web_search(monkeypatch):
    """The interview tests never reach the real web: the drug introduction (package A2) is stubbed to «no result»."""
    from backend.app.services.medication_care import drug_brief

    monkeypatch.setattr(drug_brief, "lookup", lambda name, lang, client=None: None)


@pytest.mark.parametrize(
    "text",
    [
        REQUEST,
        "هر شب ساعت ۹ یادم بنداز ویتامین D بخورم",
        "یه یادآور بذار برای داروی فشارم هر روز ساعت ۸",
        "قرصم رو هر روز ساعت ۲ بخورم",
        "remind me every day at 8 to take my pill",
        "remind me daily to take my medication at 9pm",
        "كل يوم الساعة 8 ذكّرني بدوائي",
    ],
)
def test_pill_reminders_are_detected(text):
    assert mc.is_medication_text(text)


@pytest.mark.parametrize(
    "text",
    ["یادم بنداز فردا برم داروخانه", "یادم بنداز فردا ساعت ۱۰ جلسه دارم", "remind me to go to the pharmacy tomorrow", "هر روز ساعت ۶ ورزش یادم بنداز"],
)
def test_other_reminders_are_not_medication(text):
    assert not mc.is_medication_text(text)


@pytest.mark.parametrize(
    "text, name",
    [
        ("هر روز ساعت ۸ قرص متفورمین بخورم", "متفورمین"),
        (REQUEST, None),
        ("هر روز ساعت ۸ داروی فشارم بخورم", None),
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
    assert not mc._is_recurring(None)


@pytest.mark.parametrize("text", ["همین ساعت فقط", "فقط یادم بنداز", "بدون سوال", "just remind me", "no questions please", "same time"])
def test_insistence_phrases(text):
    assert mc.insists(text)
    assert not mc.insists("برای فشار خون مصرف می‌کنم")


# --- the interview texts: ONE question, stage markers, exact name / photo ----------------------------------------
@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_every_stage_text_asks_one_question_and_is_recognised_next_turn(lang):
    ask_name = sedi_copy.t("medication.chat.q.ask_name", lang)
    confirm = sedi_copy.t("medication.chat.q.confirm_name", lang, name="Zed")
    reason = sedi_copy.t("medication.chat.q.ask_reason", lang, name="Zed")
    for text, stage in ((ask_name, "ask_name"), (confirm, "confirm_name"), (reason, "ask_reason")):
        assert text.count("?") + text.count("؟") == 1  # one question per reply (R-020/R-067)
        assert mc._stage_of(text, lang) == stage
        assert "{" not in text
    assert "photo" in ask_name.lower() or "عکس" in ask_name or "صورة" in ask_name  # exact name / photo of the box (R-088 am.3)
    assert "Zed" in confirm and "Zed" in reason
    # a created-reminder text is never mistaken for a question stage, nor is small talk
    assert mc._stage_of(sedi_copy.t("medication.chat.created.after_reason", lang, name="Zed", time="14:00"), lang) is None
    assert mc._stage_of("سلام، امروز چطوری؟", lang) is None


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_created_texts_carry_time_name_and_the_open_door(lang):
    for key in ("medication.chat.created.after_reason", "medication.chat.created.insist_named"):
        text = sedi_copy.t(key, lang, name="Zed", time="14:00")
        assert "14:00" in text and "Zed" in text and "{" not in text
    insist = sedi_copy.t("medication.chat.created.insist_named", lang, name="Zed", time="14:00")
    assert insist.count("?") + insist.count("؟") == 0  # not a question, not a menu of offers (R-049)
    unnamed = sedi_copy.t("medication.chat.created.insist_unnamed", lang, name="", time="14:00")
    assert "14:00" in unnamed and "{" not in unnamed


# --- turn 1 -----------------------------------------------------------------------------------------------------
class _Draft(SimpleNamespace):
    pass


def _draft(rule="FREQ=DAILY"):
    return _Draft(starts_at_local=datetime(2026, 11, 18, 14, 0), recurrence_rule=rule)


@pytest.fixture
def owner(monkeypatch):
    writes = []

    def fake_create(db, *, user_id, draft, language, timezone_name, name):
        writes.append(name)
        return {"kind": "medication", "created": True, "duplicate": False, "name": name or mc.provisional_name(language),
                "named": bool(name), "time": "14:00", "days": None}

    monkeypatch.setattr(mc, "_create", fake_create)
    return writes


def test_first_turn_asks_before_setting_any_time(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    out = mc.start_interview(None, user_id=1, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    assert out["created"] is False and out["interview"] == "ask_name" and owner == []
    named = mc.start_interview(None, user_id=1, message="هر روز ساعت ۸ قرص متفورمین بخورم", draft=_draft(), language="fa", timezone_name=TZ)
    assert named["interview"] == "confirm_name" and named["name"] == "متفورمین" and owner == []
    text = mc.confirmation(out, "fa", "WHEN")
    assert "کدام دارو را مصرف می‌کنی" in text and "یادت می‌اندازم" not in text  # no «I will remind you» before knowing


def test_insistence_creates_at_once_with_the_open_door(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    out = mc.start_interview(None, user_id=1, message="هر روز ساعت ۲ قرص بخورم همین ساعت", draft=_draft(), language="fa", timezone_name=TZ)
    assert out["created"] and out["flow"] == "insist" and owner == [None]
    assert "مراقب سلامتی" in mc.confirmation(out, "fa", "WHEN")


def test_without_consent_the_request_is_created_at_once_and_the_pill_is_asked(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: False)
    out = mc.start_interview(None, user_id=1, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    assert out["created"] and out["flow"] == "no_history" and owner == [None]
    assert "کدام قرص" in mc.confirmation(out, "fa", "هر روز ساعت ۱۴:۰۰")


def test_one_off_non_medication_and_kill_switch_keep_the_generic_path(monkeypatch, owner):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    assert mc.start_interview(None, user_id=1, message="فردا ساعت ۲ قرص بخورم", draft=_draft(None), language="fa", timezone_name=TZ) is None
    assert mc.start_interview(None, user_id=1, message="هر روز ساعت ۶ ورزش یادم بنداز", draft=_draft(), language="fa", timezone_name=TZ) is None
    monkeypatch.setenv(mc.DISABLED_ENV, "1")
    assert mc.start_interview(None, user_id=1, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ) is None
    assert owner == []


# --- the next turns ---------------------------------------------------------------------------------------------
def _turns(*pairs, request=REQUEST):
    """Newest first: [(user, sedi), ...] after the original request turn."""
    now = datetime.utcnow()
    rows = [SimpleNamespace(user_message=u, sedi_response=s, created_at=now) for u, s in pairs]
    rows.append(SimpleNamespace(user_message=request, sedi_response=sedi_copy.t("medication.chat.q.ask_name", "fa"), created_at=now))
    return rows


def _go(monkeypatch, rows, message, lang="fa", consent=True):
    monkeypatch.setattr(mc, "history_available", lambda db, uid: consent)
    monkeypatch.setattr(mc, "_recent_turns", lambda db, uid, now: rows)
    return mc.continue_interview(None, user_id=1, message=message, language=lang, timezone_name=TZ)


def test_name_answer_leads_to_the_reason_question_and_still_no_reminder(monkeypatch, owner):
    reply = _go(monkeypatch, _turns(), "لووتیروکسین")
    assert reply and "لووتیروکسین" in reply and mc._stage_of(reply, "fa") == "ask_reason" and owner == []


def test_reason_answer_creates_the_reminder_with_the_learned_name(monkeypatch, owner):
    ask_reason = sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین")
    rows = [SimpleNamespace(user_message="لووتیروکسین", sedi_response=ask_reason, created_at=datetime.utcnow())] + _turns()
    reply = _go(monkeypatch, rows, "برای کم‌کاری تیروئید مصرفش می‌کنم")
    assert owner == ["لووتیروکسین"] and "14:00" in reply and "لووتیروکسین" in reply and "همراهتم" in reply


def test_confirm_stage_yes_no_and_new_name(monkeypatch, owner):
    confirm = sedi_copy.t("medication.chat.q.confirm_name", "fa", name="متفورمین")

    def rows():
        return [SimpleNamespace(user_message=REQUEST, sedi_response=confirm, created_at=datetime.utcnow())]

    assert mc._stage_of(_go(monkeypatch, rows(), "بله"), "fa") == "ask_reason"
    assert mc._stage_of(_go(monkeypatch, rows(), "نه"), "fa") == "ask_name"
    renamed = _go(monkeypatch, rows(), "گلیبن کلامید")
    assert "گلیبن" in renamed and mc._stage_of(renamed, "fa") == "ask_reason" and owner == []


@pytest.mark.parametrize("message", ["همین ساعت فقط یادم بنداز", "نمی‌دونم", "فرقی نمی‌کنه", "just remind me"])
def test_insistence_or_non_answer_ends_the_interview_and_creates(monkeypatch, owner, message):
    reply = _go(monkeypatch, _turns(), message)
    assert owner == [None] and reply and "14:00" in reply
    assert "مراقب سلامتی" in reply


def test_other_topics_and_unrelated_turns_are_left_to_the_normal_flow(monkeypatch, owner):
    long_other = "راستی دیروز با دوستم رفتیم بیرون و کلی خوش گذشت و بعد هم رفتیم رستوران و غذا خوردیم و کلی حرف زدیم"
    assert _go(monkeypatch, _turns(), long_other) is None
    plain = [SimpleNamespace(user_message="سلام", sedi_response="سلام، امروز چطوری؟", created_at=datetime.utcnow())]
    assert _go(monkeypatch, plain, "خوبم") is None
    assert owner == []


def test_no_original_request_in_the_window_means_nothing_happens(monkeypatch, owner):
    rows = [SimpleNamespace(user_message="سلام", sedi_response=sedi_copy.t("medication.chat.q.ask_name", "fa"), created_at=datetime.utcnow())]
    assert _go(monkeypatch, rows, "لووتیروکسین") is None and owner == []


@pytest.mark.parametrize(
    "reply, expected",
    [("لووتیروکسین", "لووتیروکسین"), ("اسمش متفورمین هست", "متفورمین"), ("قرص آتورواستاتین", "آتورواستاتین"),
     ("Levothyroxine", "levothyroxine"), ("بله", None), ("نه", None),
     ("یک جمله‌ی خیلی بلند که اصلاً اسم قرص نیست و درباره‌ی چیز دیگری است", None)],
)
def test_candidate_name_from_a_short_reply(reply, expected):
    got = mc._candidate_name(reply)
    assert (got.lower() if got else None) == expected


def test_revoked_memory_consent_stops_the_interview_at_once(monkeypatch, owner):
    """Codex P1 (PR 185): continuation must re-check the CURRENT memory-read permission, not only the first turn."""
    ask_reason = sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین")
    rows = [SimpleNamespace(user_message="لووتیروکسین", sedi_response=ask_reason, created_at=datetime.utcnow())] + _turns()
    assert _go(monkeypatch, rows, "برای کم‌کاری تیروئید", consent=False) is None
    assert owner == []


def test_request_completed_by_a_period_answer_is_reconstructed(monkeypatch, owner):
    """Codex P2 (PR 185): «ساعت ۲» -> Sedi asks «صبح یا عصر؟» -> «عصر» -> medicine question: the stored messages are
    separate, the interview must still find the complete request."""
    period_question = sedi_copy.by_lang("reminder.clarify_opening.period")["fa"] + " ساعت ۲ صبح است یا عصر؟"
    ask_name = sedi_copy.t("medication.chat.q.ask_name", "fa")
    now = datetime.utcnow()
    rows = [
        SimpleNamespace(user_message="لووتیروکسین", sedi_response=sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین"), created_at=now),
        SimpleNamespace(user_message="عصر", sedi_response=ask_name, created_at=now),
        SimpleNamespace(user_message="هر روز ساعت ۲ یادم بنداز قرص بخورم", sedi_response=period_question, created_at=now),
    ]
    reply = _go(monkeypatch, rows, "برای کم‌کاری تیروئید مصرفش می‌کنم")
    assert owner == ["لووتیروکسین"] and reply and "14:00" in reply
