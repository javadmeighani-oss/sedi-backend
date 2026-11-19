"""R-103 step A, Codex round 1 on PR 192 (four P2): explicit dates, chained clarifications, advance-reminder lead time, medication
time collisions. DB-free; the owners are stubbed."""
from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.intelligence import reminder_reschedule as rr

NOW = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)  # 21:30 Tehran on the 19th


def _event(eid=1, title="Dentist", hh=9, mm=0, recurring=False, day=datetime(2026, 11, 19), offsets=None):
    obj = SimpleNamespace(
        id=eid, title=title, starts_at=day.replace(hour=hh, minute=mm), timezone="Asia/Tehran", reminder_offsets_json=offsets
    )
    return {"kind": "event", "obj": obj, "title": title, "hhmm": f"{hh:02d}:{mm:02d}", "recurring": recurring}


@pytest.fixture
def owners(monkeypatch):
    calls = []
    import backend.app.services.gate2_data_service as g2

    monkeypatch.setattr(g2, "update_event", lambda db, uid, eid, body: calls.append((eid, body.starts_at)) or {})
    return calls


def _go(monkeypatch, cands, message, language="en", context=""):
    monkeypatch.setattr(rr, "_candidates", lambda db, uid, now: cands)
    return rr.handle(MagicMock(), user_id=1, message=message, language=language, now_utc=NOW, context=context)


# --- P2: an explicit day wins over the event's old date --------------------------------------------------------------------
@pytest.mark.parametrize(
    "lang,message,expected_day",
    [
        ("en", "move the reminder to 4 pm tomorrow", datetime(2026, 11, 20, 16, 0)),
        ("fa", "ساعت یادآوری را فردا ساعت ۴ عصر تغییر بده", datetime(2026, 11, 20, 16, 0)),
        ("en", "move the reminder to 11 pm today", datetime(2026, 11, 19, 23, 0)),
    ],
)
def test_an_explicit_day_is_honoured(monkeypatch, owners, lang, message, expected_day):
    reply = _go(monkeypatch, [_event()], message, lang)
    assert owners == [(1, expected_day)] and f"{expected_day.hour:02d}:00" in reply


def test_an_explicit_day_that_has_passed_changes_nothing(monkeypatch, owners):
    reply = _go(monkeypatch, [_event()], "move the reminder to 4 pm today")  # 16:00 on the 19th is behind (21:30 Tehran)
    assert reply == sedi_copy.t("reminder.reschedule.past", "en") and owners == []


# --- P2: a chain of clarification questions keeps the original request ----------------------------------------------------
def test_successive_clarifications_keep_the_original_request(monkeypatch, owners):
    cands = [_event(eid=1, title="Dentist", hh=9, recurring=True), _event(eid=2, title="Workout", hh=18, recurring=True)]
    first = _go(monkeypatch, cands, "change the reminder to at 5")
    assert first == sedi_copy.t("reminder.reschedule.ask_period", "en", hour=5)
    turn1 = SimpleNamespace(user_message="change the reminder to at 5", sedi_response=first)
    second_msg = rr.pending_request([turn1], "pm", "en")
    second = _go(monkeypatch, cands, second_msg)
    assert second.startswith("Which reminder do you mean?") and owners == []
    turn0 = SimpleNamespace(user_message="pm", sedi_response=second)
    final_msg = rr.pending_request([turn0, turn1], "Dentist", "en")
    assert "change the reminder to at 5" in final_msg and final_msg.endswith("Dentist")
    reply = _go(monkeypatch, cands, final_msg, context=rr.context_of([turn0, turn1], True))
    assert owners and owners[0][0] == 1 and "17:00" in reply


def test_a_period_question_still_needs_a_period_word_as_its_answer():
    ask = sedi_copy.t("reminder.reschedule.ask_period", "en", hour=5)
    turn = SimpleNamespace(user_message="change the reminder to at 5", sedi_response=ask)
    assert rr.pending_request([turn], "whatever", "en") is None
    assert rr.pending_request([SimpleNamespace(user_message="hi", sedi_response="Hello!")], "pm", "en") is None


# --- P2: an event with an advance reminder moves, and the lead time is said ------------------------------------------------
def test_an_event_with_an_advance_reminder_says_what_stays(monkeypatch, owners):
    reply = _go(monkeypatch, [_event(offsets="[30]", recurring=True)], "move the reminder to 4 pm")
    assert owners and owners[0][1].hour == 16 and "30" in reply and "minutes before" in reply


def test_a_zero_or_missing_lead_uses_the_plain_confirmation(monkeypatch, owners):
    for raw in (None, "[]", "[0]"):
        owners.clear()
        reply = _go(monkeypatch, [_event(offsets=raw, recurring=True)], "move the reminder to 4 pm")
        assert owners and "minutes before" not in reply


# --- P2: a medication time collision changes nothing ---------------------------------------------------------------------
def test_moving_a_dose_onto_another_dose_is_refused(monkeypatch):
    from backend.app.services import user_medication_service as svc

    sent = []
    monkeypatch.setattr(svc, "move_schedule_time", lambda *a, **k: sent.append(a))
    r1 = SimpleNamespace(time_of_day=time(14, 0), days_of_week="MO")
    r2 = SimpleNamespace(time_of_day=time(20, 0), days_of_week="TU")
    um = SimpleNamespace(id=3, schedules=[r1, r2])
    cand = {"kind": "med", "obj": um, "row": r1, "title": "Metformin", "hhmm": "14:00", "recurring": True}
    reply = _go(monkeypatch, [cand], "move the reminder to 8 pm", context="Metformin")
    assert reply == sedi_copy.t("reminder.reschedule.collision", "en", title="Metformin", new="20:00") and sent == []


# --- round 2: a reminder NAMED in the message wins over the old-time filter (P1) ----------------------------------------------
def test_p1_a_named_reminder_is_not_replaced_by_a_unique_time_match(monkeypatch, owners):
    cands = [_event(eid=1, title="Aspirin", hh=9, recurring=True), _event(eid=2, title="Metformin", hh=14, recurring=True)]
    reply = _go(monkeypatch, cands, "move my Metformin reminder from 9 am to 4 pm")  # the old time 9 am belongs to Aspirin
    assert owners and owners[0][0] == 2 and "Metformin" in reply and "Aspirin" not in reply


def test_p1_the_old_time_still_picks_when_nothing_is_named(monkeypatch, owners):
    cands = [_event(eid=1, title="Aspirin", hh=9, recurring=True), _event(eid=2, title="Metformin", hh=14, recurring=True)]
    _go(monkeypatch, cands, "move the reminder from 9 am to 10 am")
    assert owners and owners[0][0] == 1


# --- round 2: the medication move is ONE owner call that keeps the weekday filter (P2) ------------------------------------------
def test_p2_move_schedule_time_is_in_place_atomic_and_keeps_the_weekday_filter(monkeypatch):
    from backend.app.services import user_medication_service as svc

    r1 = SimpleNamespace(time_of_day=time(14, 0), days_of_week="MO")
    r2 = SimpleNamespace(time_of_day=time(20, 0), days_of_week="TU")
    um = SimpleNamespace(id=3, schedules=[r1, r2], updated_at=None)
    db = MagicMock()
    monkeypatch.setattr(svc, "get_user_medication_owned", lambda d, uid, umid: (um, SimpleNamespace(name="X")))
    monkeypatch.setattr(svc, "build_user_medication_out", lambda u, m: {"id": u.id})
    assert svc.move_schedule_time(db, 1, 3, "14:00", "16:00") == {"id": 3}
    assert r1.time_of_day == time(16, 0) and r1.days_of_week == "MO" and r2.time_of_day == time(20, 0) and r2.days_of_week == "TU"
    assert db.commit.call_count == 1  # one transaction, no intermediate daily schedule
    with pytest.raises(svc.ScheduleTimeCollisionError):
        svc.move_schedule_time(db, 1, 3, "16:00", "20:00")
    with pytest.raises(svc.UserMedicationNotFoundError):
        svc.move_schedule_time(db, 1, 3, "07:00", "08:00")
    assert db.commit.call_count == 1  # the refused moves committed nothing


# --- round 3: the event keeps its duration (P2) ---------------------------------------------------------------------------------
def test_p2_a_populated_end_time_moves_with_the_start(monkeypatch):
    import backend.app.services.gate2_data_service as g2

    seen = []
    monkeypatch.setattr(g2, "update_event", lambda db, uid, eid, body: seen.append((body.starts_at, body.ends_at)) or {})
    ev = _event(hh=9, recurring=True)
    ev["obj"].ends_at = datetime(2026, 11, 19, 10, 0)
    _go(monkeypatch, [ev], "move the reminder to 4 pm")
    assert seen == [(datetime(2026, 11, 19, 16, 0), datetime(2026, 11, 19, 17, 0))]  # 09:00-10:00 -> 16:00-17:00
    seen.clear()
    ev2 = _event(hh=9, recurring=True)
    ev2["obj"].ends_at = None
    _go(monkeypatch, [ev2], "move the reminder to 4 pm")
    assert seen == [(datetime(2026, 11, 19, 16, 0), None)]


# --- round 4: roles of two clocks, and an expired one-time reminder -------------------------------------------------------------
@pytest.mark.parametrize(
    "lang,message",
    [
        ("en", "change the reminder to 4 pm instead of 2 pm"),
        ("en", "change the reminder to 4 pm, the 2 pm one"),
        ("fa", "ساعت یادآوری را به ۴ عصر تغییر بده به جای ۲ بعدازظهر"),
        ("en", "change the reminder from 2 pm to 4 pm"),
    ],
)
def test_p2_the_destination_is_found_by_its_role_not_by_position(monkeypatch, owners, lang, message):
    cands = [_event(eid=1, title="Dentist", hh=14, recurring=True), _event(eid=2, title="Workout", hh=9, recurring=True)]
    reply = _go(monkeypatch, cands, message, lang)
    assert owners and owners[0][0] == 1 and owners[0][1].hour == 16 and "16:00" in reply


def test_p2_an_identifying_time_in_a_clarification_answer_never_replaces_the_destination(monkeypatch, owners):
    cands = [_event(eid=1, title="Dentist", hh=9, recurring=True), _event(eid=2, title="Workout", hh=18, recurring=True)]
    combined = "change the reminder to 5 pm Dentist at 9 am"
    reply = _go(monkeypatch, cands, combined)
    assert owners and owners[0][0] == 1 and owners[0][1].hour == 17 and "17:00" in reply


def test_p2_an_expired_one_time_reminder_moves_to_the_next_future_occurrence(monkeypatch, owners):
    # yesterday 23:00 (still inside the 24 h candidate cutoff); 16:00 today is behind now (21:30 Tehran) -> tomorrow 16:00
    ev = _event(title="Dentist", hh=23, recurring=False, day=datetime(2026, 11, 18))
    reply = _go(monkeypatch, [ev], "move the reminder to 4 pm")
    assert owners == [(1, datetime(2026, 11, 20, 16, 0))] and sedi_copy.t("reminder.reschedule.day_tomorrow", "en") in reply


# --- round 5 --------------------------------------------------------------------------------------------------------------------
def test_p1_the_previous_reply_alone_never_makes_a_message_about_a_reminder(monkeypatch, owners):
    cands = [_event(title="Supplement", hh=9, recurring=True)]
    assert _go(monkeypatch, cands, "change my dinner to 8 pm", context="I will remind you to take Supplement at 9.") is None
    assert owners == []
    # the previous reply still helps CHOOSE once the message does point at a reminder
    two = [_event(eid=1, title="Supplement", hh=9, recurring=True), _event(eid=2, title="Workout", hh=18, recurring=True)]
    assert _go(monkeypatch, two, "change the reminder to 8 pm", context="I will remind you to take Supplement at 9.")
    assert owners and owners[0][0] == 1


def test_p2_a_new_complete_request_replaces_the_pending_one():
    ask = sedi_copy.t("reminder.reschedule.ask_which", "en", list="“Dentist” 09:00; “Workout” 18:00")
    turn = SimpleNamespace(user_message="change the reminder to 5 pm", sedi_response=ask)
    assert rr.pending_request([turn], "Actually move Dentist to 6 pm", "en") is None  # handled on its own
    assert rr.pending_request([turn], "Dentist", "en") == "change the reminder to 5 pm Dentist"


def test_p2_a_new_complete_request_through_the_flow_uses_its_own_time(monkeypatch, owners):
    cands = [_event(eid=1, title="Dentist", hh=9, recurring=True), _event(eid=2, title="Workout", hh=18, recurring=True)]
    _go(monkeypatch, cands, "Actually move my Dentist reminder to 6 pm")
    assert owners and owners[0][0] == 1 and owners[0][1].hour == 18


@pytest.mark.parametrize(
    "lang,message",
    [
        ("en", "move only tomorrow's reminder to 4 pm"), ("en", "just for today move the reminder to 4 pm"),
        ("fa", "فقط فردا ساعت یادآوری را ۴ عصر کن و تغییر بده"), ("fa", "ساعت یادآوری را فقط امروز به ۴ عصر تغییر بده"),
    ],
)
def test_p2_a_one_day_change_never_rewrites_a_repeating_series(monkeypatch, owners, lang, message):
    reply = _go(monkeypatch, [_event(title="Supplement", hh=14, recurring=True)], message, lang)
    assert reply == sedi_copy.t("reminder.reschedule.series_only", lang, title="Supplement") and owners == []


def test_p2_a_one_time_reminder_may_still_use_a_day_word(monkeypatch, owners):
    _go(monkeypatch, [_event(title="Dentist", hh=9, recurring=False, day=datetime(2026, 11, 20))], "move only tomorrow's reminder to 4 pm")
    assert owners and owners[0][1] == datetime(2026, 11, 20, 16, 0)


# --- round 6: a change verb inside the TASK of a new reminder is not a reschedule ---------------------------------------------------
@pytest.mark.parametrize(
    "lang,message",
    [
        ("en", "remind me to change my bandage at 4 pm"), ("en", "please remind me to move the car at 4 pm"),
        ("fa", "یادم بنداز ساعت ۴ عصر پانسمانم را عوض کنم"), ("fa", "ساعت ۴ عصر یادم بنداز لباسم را عوض کنم"),
    ],
)
def test_p1_a_new_reminder_with_a_change_verb_in_its_task_is_left_to_the_normal_flow(monkeypatch, owners, lang, message):
    assert rr.is_change_request(message) is False
    assert _go(monkeypatch, [_event(title="Supplement", hh=9, recurring=True)], message, lang) is None and owners == []


@pytest.mark.parametrize(
    "lang,message",
    [
        ("en", "remind me again but change the reminder time to 4 pm"), ("en", "change the reminder time to 4 pm"),
        ("fa", "زمانش را تغییر بده به ۴ عصر"), ("fa", "یادم بنداز، ساعت یادآوری رو تغییر بده به ۴ عصر"),
    ],
)
def test_p1_an_explicit_target_still_counts_as_a_reschedule(monkeypatch, owners, lang, message):
    assert rr.is_change_request(message) is True
    assert _go(monkeypatch, [_event(title="Supplement", hh=9, recurring=True)], message, lang)
    assert owners and owners[0][1].hour == 16


# --- round 7: «from 9 am to 4» - the bare destination is ambiguous, never replaced by the source ------------------------------------
@pytest.mark.parametrize(
    "lang,message,hour",
    [
        ("en", "change the reminder from 9 am to 4", 4),
        ("fa", "ساعت یادآوری را از ساعت ۹ صبح به ۴ تغییر بده", 4),
    ],
)
def test_p2_a_bare_destination_after_from_asks_for_the_period(monkeypatch, owners, lang, message, hour):
    reply = _go(monkeypatch, [_event(title="Supplement", hh=9, recurring=True)], message, lang)
    assert reply == sedi_copy.t("reminder.reschedule.ask_period", lang, hour=hour) and owners == []


def test_p2_the_bare_destination_with_its_period_answer_finishes(monkeypatch, owners):
    cands = [_event(title="Supplement", hh=9, recurring=True)]
    ask = _go(monkeypatch, cands, "change the reminder from 9 am to 4")
    turn = SimpleNamespace(user_message="change the reminder from 9 am to 4", sedi_response=ask)
    combined = rr.pending_request([turn], "pm", "en")
    reply = _go(monkeypatch, cands, combined)
    assert owners and owners[0][1].hour == 16 and "16:00" in reply
