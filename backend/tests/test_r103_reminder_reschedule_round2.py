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
    monkeypatch.setattr(svc, "update_user_medication", lambda *a, **k: sent.append(a))
    r1 = SimpleNamespace(time_of_day=time(14, 0), days_of_week="MO")
    r2 = SimpleNamespace(time_of_day=time(20, 0), days_of_week="TU")
    um = SimpleNamespace(id=3, schedules=[r1, r2])
    cand = {"kind": "med", "obj": um, "row": r1, "title": "Metformin", "hhmm": "14:00", "recurring": True}
    reply = _go(monkeypatch, [cand], "move the reminder to 8 pm", context="Metformin")
    assert reply == sedi_copy.t("reminder.reschedule.collision", "en", title="Metformin", new="20:00") and sent == []
