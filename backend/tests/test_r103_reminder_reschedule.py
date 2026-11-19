"""R-103 step A (pilot 2026-11-19): «change the time of my reminder» from chat REALLY changes it; the model can no longer claim it.

DB-free: the reminder owners are stubbed (update_event / update_user_medication); detection, time extraction, anchoring, the
two clarification questions, the honest failure and the guard run for real. Matrix: wording x language x situation.
"""
from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.intelligence import grounding_guard as gg
from backend.app.services.intelligence import reminder_reschedule as rr

NOW = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)  # 21:30 Tehran
PILL_CTX = "بله جواد، گفته بودی هر روز ساعت ۲ بعدازظهر خوردن مکملت را به تو یادآوری کنم."


def _event(eid=15, title="خوردن قرص مکملم", hh=14, mm=0, recurring=True, day=datetime(2026, 11, 12)):
    obj = SimpleNamespace(id=eid, title=title, starts_at=day.replace(hour=hh, minute=mm), timezone="Asia/Tehran")
    return {"kind": "event", "obj": obj, "title": title, "hhmm": f"{hh:02d}:{mm:02d}", "recurring": recurring}


@pytest.fixture
def owners(monkeypatch):
    calls = []
    import backend.app.services.gate2_data_service as g2

    monkeypatch.setattr(g2, "update_event", lambda db, uid, eid, body: calls.append((eid, body.starts_at)) or {})
    return calls


def _with(monkeypatch, cands):
    monkeypatch.setattr(rr, "_candidates", lambda db, uid, now: cands)


def _go(message, language="fa", context="", now=NOW):
    return rr.handle(MagicMock(), user_id=1, message=message, language=language, now_utc=now, context=context)


# --- the pilot scenario ------------------------------------------------------------------------------------------------
def test_the_pilot_request_really_moves_the_daily_pill_reminder(monkeypatch, owners):
    _with(monkeypatch, [_event()])
    reply = _go("میخواهم زمانشو تغییر بدم به ساعت ۴ عصر", context=PILL_CTX)
    assert owners == [(15, datetime(2026, 11, 12, 16, 0))]  # same anchor date, new wall-clock time; the rule stays DAILY
    assert "خوردن قرص مکملم" in reply and "14:00" in reply and "16:00" in reply and "تغییر دادم" in reply
    assert reply.count("?") + reply.count("؟") == 0


@pytest.mark.parametrize(
    "lang,message",
    [
        ("fa", "زمانش رو بکن ۴ عصر"), ("fa", "ساعت یادآوری قرص رو از ۲ به ۴ عصر تغییر بده"),
        ("en", "change the reminder from 2 pm to 4 pm"), ("en", "move it to 4 pm"),
        ("ar", "غيّر موعد التذكير إلى الساعة 4 مساء"),
    ],
)
def test_wording_matrix_all_reach_the_owner(monkeypatch, owners, lang, message):
    _with(monkeypatch, [_event()])
    reply = _go(message, lang, context=PILL_CTX)
    assert owners and owners[0][1].hour == 16 and "16:00" in reply


# --- honesty / anchoring -------------------------------------------------------------------------------------------------
def test_a_message_that_is_not_about_a_reminder_is_left_alone(monkeypatch, owners):
    _with(monkeypatch, [_event()])
    assert _go("change my dinner to 8 pm", "en") is None
    assert _go("یادم بنداز ساعت ۴ دارو بخورم", "fa") is None  # a NEW reminder has no change verb
    assert owners == []


def test_no_reminder_means_the_normal_flow_not_a_claim(monkeypatch, owners):
    _with(monkeypatch, [])
    assert _go("زمانشو بکن ۴ عصر") is None and owners == []


def test_a_failed_write_says_so_and_claims_nothing(monkeypatch):
    import backend.app.services.gate2_data_service as g2

    monkeypatch.setattr(g2, "update_event", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db")))
    _with(monkeypatch, [_event()])
    reply = _go("زمانشو بکن ۴ عصر", context=PILL_CTX)
    assert reply == sedi_copy.t("reminder.reschedule.failed", "fa") and "تغییر دادم" not in reply


# --- one question when unsure --------------------------------------------------------------------------------------------
def test_an_ambiguous_hour_asks_morning_or_evening_then_finishes(monkeypatch, owners):
    _with(monkeypatch, [_event()])
    ask = _go("زمانشو تغییر بدم به ساعت ۴", context=PILL_CTX)
    assert ask == sedi_copy.t("reminder.reschedule.ask_period", "fa", hour=4) and owners == []
    assert ask.count("؟") == 1
    combined = rr.pending_prior_request(ask, "زمانشو تغییر بدم به ساعت ۴", "عصر", "fa")
    assert combined and "عصر" in combined
    assert "16:00" in _go(combined, context=PILL_CTX) and owners[0][1].hour == 16
    assert rr.pending_prior_request(ask, "زمانشو تغییر بدم به ساعت ۴", "نمی‌دانم", "fa") is None  # no period word: not an answer


def test_two_reminders_and_no_clue_ask_which_one_then_finish(monkeypatch, owners):
    _with(monkeypatch, [_event(), _event(eid=20, title="جلسه‌ی هفتگی", hh=9)])
    ask = _go("ساعت یادآوری رو تغییر بده به ۵ عصر")
    assert ask.startswith("کدام یادآوری را می‌گویی؟") and "جلسه‌ی هفتگی" in ask and owners == []
    assert ask.count("؟") == 1
    combined = rr.pending_prior_request(ask, "ساعت یادآوری رو تغییر بده به ۵ عصر", "همان قرص مکمل", "fa")
    assert "17:00" in _go(combined) and owners[0][0] == 15


def test_the_old_time_in_the_message_picks_the_reminder(monkeypatch, owners):
    _with(monkeypatch, [_event(), _event(eid=20, title="جلسه‌ی هفتگی", hh=9)])
    reply = _go("ساعت یادآوری رو از ۹ صبح تغییر بده به ۱۰ صبح")
    assert owners and owners[0][0] == 20 and "جلسه‌ی هفتگی" in reply


# --- one-time reminders: the next time that clock shows ----------------------------------------------------------------
def test_a_one_time_reminder_keeps_its_date_when_the_new_time_is_still_ahead(monkeypatch, owners):
    _with(monkeypatch, [_event(eid=16, title="هم قرصمو بخورم", hh=9, recurring=False, day=datetime(2026, 11, 20))])
    reply = _go("ساعت یادآوری قرص رو تغییر بده به ۸ شب")  # tomorrow 20:00 is ahead of now (21:30 Tehran, the 19th)
    assert owners and owners[0][1] == datetime(2026, 11, 20, 20, 0)
    assert "20:00" in reply and sedi_copy.t("reminder.reschedule.day_tomorrow", "fa") in reply


def test_a_one_time_reminder_whose_new_time_has_passed_rolls_to_the_next_day(monkeypatch, owners):
    _with(monkeypatch, [_event(eid=16, title="هم قرصمو بخورم", hh=23, recurring=False, day=datetime(2026, 11, 19))])
    _go("ساعت یادآوری قرص رو تغییر بده به ۸ شب")  # 20:00 on the 19th is already behind (21:30 Tehran) -> the 20th
    assert owners and owners[0][1] == datetime(2026, 11, 20, 20, 0)


# --- the medication owner ---------------------------------------------------------------------------------------------------
def test_a_medication_schedule_is_changed_through_its_owner(monkeypatch):
    from backend.app.services import user_medication_service as svc

    sent = []
    monkeypatch.setattr(svc, "move_schedule_time", lambda db, uid, umid, old, new: sent.append((umid, old, new)) or {})
    row = SimpleNamespace(time_of_day=time(14, 0), days_of_week="MO,TU")
    um = SimpleNamespace(id=3, schedules=[row])
    _with(monkeypatch, [{"kind": "med", "obj": um, "row": row, "title": "لووتیروکسین", "hhmm": "14:00", "recurring": True}])
    reply = _go("زمانش رو بکن ۴ عصر", context="لووتیروکسین")
    assert sent == [(3, "14:00", "16:00")] and "لووتیروکسین" in reply and "16:00" in reply


# --- the guard: the model can no longer claim a change ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "lang,reply",
    [
        ("fa", "حتماً جواد؛ یادآوری روزانه‌ی خوردن قرص را از ساعت ۲ به ۴ عصر تغییر دادم."),
        ("en", "Sure, I changed your reminder to 4 pm."),
        ("en", "Done - I have moved the reminder to 4 pm."),
        ("ar", "حسناً، غيّرت التذكير إلى الساعة 4 مساء."),
    ],
)
def test_the_guard_removes_an_unperformed_change_claim(lang, reply):
    out = gg.strip_unverified_change_claims(reply, lang)
    assert out == sedi_copy.t("reminder.change_not_done", lang)


def test_the_guard_keeps_denials_and_other_sentences():
    assert gg.strip_unverified_change_claims("I have not changed the reminder yet.", "en") == "I have not changed the reminder yet."
    mixed = "Walking after dinner helps digestion. I changed your reminder to 4 pm."
    assert gg.strip_unverified_change_claims(mixed, "en") == "Walking after dinner helps digestion."
    assert gg.strip_unverified_change_claims("امروز هوا خوب است.", "fa") == "امروز هوا خوب است."


# --- through the REAL orchestrator ------------------------------------------------------------------------------------------
def test_the_orchestrator_answers_the_pilot_request_with_a_real_change(monkeypatch, owners):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app.services.medication_care import chat_reminder as mc

    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    monkeypatch.setattr(
        mc, "_recent_turns", lambda db, uid, now: [SimpleNamespace(user_message="x", sedi_response=PILL_CTX, created_at=datetime.utcnow())]
    )
    _with(monkeypatch, [_event()])
    called = {"gen": False}

    def gen(*a, **k):
        called["gen"] = True
        return {"message": "SHOULD NOT APPEAR", "detected_name": None}

    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=gen, structured_mode=False)
    out = orch.process(authenticated_user_id=42, message="میخواهم زمانشو تغییر بدم به ساعت ۴ عصر", language="fa")
    assert owners and owners[0][1].hour == 16 and called["gen"] is False
    assert "R103_REMINDER_RESCHEDULE" in out.reason_codes and "16:00" in out.message


# --- Codex review of PR 192 -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "lang,message",
    [
        ("en", "don't change my reminder to 4 pm"), ("en", "please do not move the reminder to 4 pm"), ("en", "never change it to 4 pm"),
        ("fa", "زمانش را ساعت ۴ عصر تغییر نده"), ("fa", "نمی‌خوام ساعت یادآوری رو به ۴ عصر تغییر بدم"),
        ("ar", "لا تغيّر التذكير إلى الساعة 4 مساء"),
    ],
)
def test_p1_a_negated_instruction_never_changes_a_reminder(monkeypatch, owners, lang, message):
    _with(monkeypatch, [_event()])
    assert rr.is_change_request(message) is False
    assert _go(message, lang, context=PILL_CTX) is None and owners == []


def test_p1_each_time_is_resolved_with_its_own_period(monkeypatch, owners):
    times = rr._times_in(rr._norm("ساعت یادآوری را از ساعت ۴ عصر به ساعت ۹ صبح تغییر بده"))
    assert [(h, m) for h, m, _s, _w, _p in times] == [(16, 0), (9, 0)]
    en = rr._times_in(rr._norm("change the reminder from 4 pm to 9 am"))
    assert [(h, m) for h, m, _s, _w, _p in en] == [(16, 0), (9, 0)]
    _with(monkeypatch, [_event(hh=16), _event(eid=20, title="جلسه‌ی هفتگی", hh=8)])
    reply = _go("ساعت یادآوری را از ساعت ۴ عصر به ساعت ۹ صبح تغییر بده")
    assert owners and owners[0][0] == 15 and owners[0][1].hour == 9 and "16:00" not in reply.split("به ساعت")[-1]
    assert "09:00" in reply


def test_p1_an_ambiguous_new_time_is_judged_by_its_own_words_only(monkeypatch, owners):
    _with(monkeypatch, [_event()])
    ask = _go("ساعت یادآوری را از ساعت ۲ عصر به ساعت ۵ تغییر بده")  # «عصر» belongs to the OLD time; 5 is still ambiguous
    assert ask == sedi_copy.t("reminder.reschedule.ask_period", "fa", hour=5) and owners == []


def test_p2_the_clarification_options_are_not_part_of_the_selection_context(monkeypatch, owners):
    cands = [_event(eid=1, title="Dentist", hh=9), _event(eid=2, title="Workout", hh=18)]
    _with(monkeypatch, cands)
    ask = _go("change the reminder time to 5 pm", "en")
    assert ask.startswith("Which reminder do you mean?") and "Dentist" in ask and "Workout" in ask
    turns = [SimpleNamespace(user_message="change the reminder time to 5 pm", sedi_response=ask)]
    assert rr.context_of(turns, answered_question=True) == ""  # the question (all options) is excluded
    combined = rr.pending_prior_request(ask, "change the reminder time to 5 pm", "Dentist", "en")
    assert "17:00" in _go(combined, "en", context=rr.context_of(turns, True)) and owners[0][0] == 1
