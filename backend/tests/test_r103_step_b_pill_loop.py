"""R-103 step B (pilot 2026-11-19): every pill request enters ONE care loop.

 - a pill request with no day word is another DAILY series (Javad 2026-11-19);
 - a pill request with a DAY word makes Sedi ask «just once, or repeating?» and create nothing before the answer (am.2);
 - when the user already has pills Sedi asks «the same pill or a new one?»; «same» adds a dose to a registered pill or PROMOTES an
   older reminder into the medicine owner (the older event is soft-cancelled in the SAME transaction);
 - the pill's title is clean («قرص مکمل», not «هم قرصمو بخورم»).
DB-free: the registry and the owner writes are stubbed; routing, stages, answers and the guards run for real.
"""
from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.medication_care import chat_reminder as mc
from backend.app.services.medication_care import pill_registry as reg

TZ = "Asia/Tehran"
NOW = datetime(2026, 11, 19, 18, 0, tzinfo=timezone.utc)
DAILY_REQ = "هر روز ساعت ۲ بعدازظهر یادم بنداز قرص بخورم"
NO_DAY_REQ = "ساعت ۹ صبح یادم بنداز قرص بخورم"
DAY_REQ = "فردا ساعت ۹ صبح یادم بنداز قرص بخورم"


def _pill(kind="med", name="قرص مکمل", times=("14:00",), pid=3):
    return {"kind": kind, "id": pid, "name": name, "times": list(times), "rule": "FREQ=DAILY" if kind == "event" else None}


@pytest.fixture
def world(monkeypatch):
    """pills the user has + a log of owner writes."""
    state = SimpleNamespace(pills=[], added=[], promoted=[], created=[], history=True, once=[])
    monkeypatch.setattr(mc, "history_available", lambda db, uid: state.history)
    monkeypatch.setattr(reg, "existing_pills", lambda db, uid: list(state.pills))
    monkeypatch.setattr(reg, "add_dose", lambda db, uid, pill, hhmm, days, from_tz=None: state.added.append((pill["id"], hhmm)) or sorted(pill["times"] + [hhmm]))
    monkeypatch.setattr(reg, "promote", lambda db, uid, pill, hhmm, days, from_tz=None: state.promoted.append((pill["id"], hhmm)) or sorted(pill["times"] + [hhmm]))
    monkeypatch.setattr(reg, "times_of", lambda db, uid, name: ["09:00", "14:00"])

    def fake_create(db, *, user_id, draft, language, timezone_name, name):
        state.created.append(name)
        return {"kind": "medication", "created": True, "duplicate": False, "name": name or mc.provisional_name(language), "named": bool(name), "time": "09:00", "days": None}

    monkeypatch.setattr(mc, "_create", fake_create)
    monkeypatch.setattr(mc, "_once_event", lambda db, uid, draft, text, lang, tz: state.once.append(text) or "ONCE-EVENT")
    from backend.app.services.medication_care import drug_brief

    monkeypatch.setattr(drug_brief, "lookup", lambda name, lang, client=None: None)
    return state


def _draft_of(message, lang="fa"):
    from backend.app.services.intelligence.reminder_event_readiness import parse_reminder_event_draft

    draft, missing = parse_reminder_event_draft(message=message, timezone_name=TZ, now_utc=NOW, language=lang)
    assert draft is not None and missing is None, (message, missing)
    return draft


def _start(message, lang="fa"):
    return mc.start_interview(None, user_id=1, message=message, draft=_draft_of(message, lang), language=lang, timezone_name=TZ)


def _rows(*pairs):
    now = datetime.utcnow()
    return [SimpleNamespace(user_message=u, sedi_response=s, created_at=now) for u, s in pairs]


def _go(monkeypatch, rows, message, lang="fa"):
    monkeypatch.setattr(mc, "_recent_turns", lambda db, uid, now: rows)
    return mc.continue_interview(MagicMock(), user_id=1, message=message, language=lang, timezone_name=TZ)


# --- routing -----------------------------------------------------------------------------------------------------------------------
def test_no_day_word_is_a_daily_series_and_starts_the_interview(world):
    out = _start(NO_DAY_REQ)
    assert out and out["interview"] == "ask_name" and not out["created"] and world.created == []


def test_a_day_word_asks_once_or_repeating_and_creates_nothing(world):
    out = _start(DAY_REQ)
    assert out["interview"] == "ask_repeat" and not out["created"] and world.created == []
    text = mc.confirmation(out, "fa", "فردا ساعت 09:00")
    assert "فردا ساعت 09:00" in text and text.count("؟") == 1 and mc._stage_of(text, "fa") == "ask_repeat"


def test_a_day_word_without_a_place_for_the_question_keeps_the_plain_event(world):
    world.history = False
    assert _start(DAY_REQ) is None  # the plain one-time event, as before


def test_registered_pill_and_no_name_asks_same_or_new(world):
    world.pills = [_pill()]
    out = _start(NO_DAY_REQ)
    assert out["interview"] == "ask_same" and "قرص مکمل" in out["names"]
    text = mc.confirmation(out, "fa", "")
    assert mc._stage_of(text, "fa") == "ask_same" and text.count("؟") == 1


def test_a_named_pill_that_exists_adds_a_dose_without_a_question(world):
    world.pills = [_pill(name="لووتیروکسین", times=("07:00",))]
    out = _start("ساعت ۹ صبح یادم بنداز قرص لووتیروکسین بخورم")
    assert out["flow"] == "dose_added" and world.added == [(3, "09:00")]
    text = mc.confirmation(out, "fa", "")
    assert "لووتیروکسین" in text and "09:00" in text


def test_a_named_new_pill_goes_to_the_ordinary_interview(world):
    world.pills = [_pill(name="لووتیروکسین")]
    out = _start("ساعت ۹ صبح یادم بنداز قرص متفورمین بخورم")
    assert out["interview"] == "confirm_name" and world.added == [] and world.promoted == []


def test_an_older_reminder_named_again_is_promoted_and_the_reason_is_asked(world):
    world.pills = [_pill(kind="event", name="قرص مکمل", pid=15)]
    out = _start("ساعت ۹ صبح یادم بنداز قرص مکمل بخورم")
    assert out["interview"] == "ask_reason_promoted" and world.promoted == [(15, "09:00")]
    text = mc.confirmation(out, "fa", "")
    assert "قرص مکمل" in text and mc._stage_of(text, "fa") == "ask_reason_promoted" and text.count("؟") == 1


def test_promotion_without_a_place_for_the_question_closes_at_once(world):
    world.pills = [_pill(kind="event", name="قرص مکمل", pid=15)]
    world.history = False
    out = _start("ساعت ۹ صبح یادم بنداز قرص مکمل بخورم")
    assert out["flow"] == "promoted" and world.promoted == [(15, "09:00")]


@pytest.mark.parametrize("lang,req", [("en", "remind me every day at 9 am to take a pill"), ("ar", "كل يوم الساعة 9 صباحا ذكرني بتناول دوائي")])
def test_the_other_languages_follow_the_same_routing(world, lang, req):
    world.pills = [_pill(name="Vitamin", times=("07:00",))]
    out = _start(req, lang)
    assert out and out["interview"] == "ask_same"
    assert mc._stage_of(mc.confirmation(out, lang, ""), lang) == "ask_same"


# --- the answers --------------------------------------------------------------------------------------------------------------------
def _ask_same_rows(request=NO_DAY_REQ, names="«قرص مکمل»"):
    return _rows(("", sedi_copy.t("medication.chat.q.ask_same", "fa", names=names)), (request, sedi_copy.t("medication.chat.q.ask_same", "fa", names=names)))[1:]


def test_same_adds_a_dose_to_the_registered_pill(monkeypatch, world):
    world.pills = [_pill()]
    rows = _rows((NO_DAY_REQ, sedi_copy.t("medication.chat.q.ask_same", "fa", names="«قرص مکمل»")))
    reply = _go(monkeypatch, rows, "همان")
    assert world.added == [(3, "09:00")] and "قرص مکمل" in reply and "09:00" in reply


def test_new_goes_to_the_name_question(monkeypatch, world):
    world.pills = [_pill()]
    rows = _rows((NO_DAY_REQ, sedi_copy.t("medication.chat.q.ask_same", "fa", names="«قرص مکمل»")))
    assert _go(monkeypatch, rows, "یک قرص جدید") == sedi_copy.t("medication.chat.q.ask_name", "fa") and world.added == []


def test_an_unclear_answer_asks_again_and_changes_nothing(monkeypatch, world):
    world.pills = [_pill(), _pill(name="ویتامین دی", pid=4)]
    rows = _rows((NO_DAY_REQ, sedi_copy.t("medication.chat.q.ask_same", "fa", names="«قرص مکمل»، «ویتامین دی»")))
    reply = _go(monkeypatch, rows, "همان")  # two pills: «same» alone cannot say which
    assert mc._stage_of(reply, "fa") == "ask_same" and world.added == []
    assert _go(monkeypatch, rows, "ویتامین دی") and world.added == [(4, "09:00")]


def test_same_on_an_older_reminder_promotes_it(monkeypatch, world):
    world.pills = [_pill(kind="event", pid=15)]
    rows = _rows((NO_DAY_REQ, sedi_copy.t("medication.chat.q.ask_same", "fa", names="«قرص مکمل»")))
    reply = _go(monkeypatch, rows, "همون")
    assert world.promoted == [(15, "09:00")] and mc._stage_of(reply, "fa") == "ask_reason_promoted"


def test_insistence_on_the_same_question_creates_the_request_unnamed(monkeypatch, world):
    world.pills = [_pill()]
    rows = _rows((NO_DAY_REQ, sedi_copy.t("medication.chat.q.ask_same", "fa", names="«قرص مکمل»")))
    reply = _go(monkeypatch, rows, "فقط یادم بنداز")
    assert world.created == [None] and "09:00" in reply and world.added == []


def test_once_creates_the_plain_event(monkeypatch, world):
    rows = _rows((DAY_REQ, sedi_copy.t("medication.chat.q.ask_repeat", "fa", when="فردا ساعت 09:00")))
    assert _go(monkeypatch, rows, "فقط یک‌بار") == "ONCE-EVENT" and world.once == [DAY_REQ] and world.created == []


def test_every_day_starts_the_daily_interview(monkeypatch, world):
    rows = _rows((DAY_REQ, sedi_copy.t("medication.chat.q.ask_repeat", "fa", when="فردا ساعت 09:00")))
    reply = _go(monkeypatch, rows, "هر روز تکرار شود")
    assert reply == sedi_copy.t("medication.chat.q.ask_name", "fa") and world.once == []


def test_an_unclear_answer_to_once_or_repeat_asks_again(monkeypatch, world):
    rows = _rows((DAY_REQ, sedi_copy.t("medication.chat.q.ask_repeat", "fa", when="فردا ساعت 09:00")))
    reply = _go(monkeypatch, rows, "بستگی دارد به شرایط")
    assert mc._stage_of(reply, "fa") == "ask_repeat" and world.once == [] and world.created == []


def test_insistence_on_once_or_repeat_keeps_the_request_as_one_time(monkeypatch, world):
    rows = _rows((DAY_REQ, sedi_copy.t("medication.chat.q.ask_repeat", "fa", when="فردا ساعت 09:00")))
    assert _go(monkeypatch, rows, "فقط یادم بنداز") == "ONCE-EVENT"


@pytest.mark.parametrize("answer", ["لغو", "یادآوری رو نمی‌خوام"])
def test_cancel_at_the_new_questions_creates_nothing(monkeypatch, world, answer):
    rows = _rows((DAY_REQ, sedi_copy.t("medication.chat.q.ask_repeat", "fa", when="فردا ساعت 09:00")))
    assert _go(monkeypatch, rows, answer) == sedi_copy.t("medication.chat.cancelled", "fa")
    assert world.created == [] and world.once == []


# --- the reason after a promotion ---------------------------------------------------------------------------------------------------
def test_the_reason_after_a_promotion_becomes_one_tracked_commitment(monkeypatch, world):
    from backend.app.services.i10 import commitment_followup as cf

    seen = []
    monkeypatch.setattr(cf, "capture_step", lambda db, uid, step, *, user_message="": seen.append(step) or SimpleNamespace(id=1))
    ask = sedi_copy.t("medication.chat.q.ask_reason_promoted", "fa", name="قرص مکمل", times="09:00، 14:00")
    reply = _go(monkeypatch, _rows(("هم", ask)), "برای کمبود ویتامین")
    assert len(seen) == 1 and "قرص مکمل" in seen[0]
    assert sedi_copy.t("medication.chat.created.followup_promise", "fa") in reply and "09:00" in reply
    seen.clear()
    reply2 = _go(monkeypatch, _rows(("هم", ask)), "نمی‌دانم")
    assert seen == [] and sedi_copy.t("medication.chat.created.followup_promise", "fa") not in reply2


# --- registry helpers ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "title,expected",
    [("خوردن قرص مکملم", "قرص مکمل"), ("هم قرصمو بخورم", "قرص"), ("take my vitamin D", "vitamin d"), ("قرص لووتیروکسین بخورم", "قرص لووتیروکسین")],
)
def test_pill_titles_are_cleaned(title, expected):
    assert reg.pill_title_name(title) == expected


def test_same_pill_matching():
    assert reg.same_pill("قرص مکمل", "مکمل") and reg.same_pill("لووتیروکسین", "قرص لووتیروکسین")
    assert not reg.same_pill("لووتیروکسین", "متفورمین") and not reg.same_pill("قرص مکمل", "قرص لووتیروکسین")


def test_pick_and_says_new():
    pills = [_pill(), _pill(name="ویتامین دی", pid=4)]
    assert reg.pick("ویتامین دی", pills)["id"] == 4 and reg.pick("همان", pills) is None
    assert reg.pick("همان", [pills[0]])["id"] == 3
    assert reg.says_new("یک قرص جدید") and reg.says_new("another one") and not reg.says_new("همان")


def test_day_words():
    assert reg.has_day_word("فردا ساعت ۹ قرص بخورم", TZ, NOW) and reg.has_day_word("tomorrow at 9 take a pill", TZ, NOW)
    assert not reg.has_day_word("ساعت ۹ صبح قرص بخورم", TZ, NOW)


# --- the medicine owner: atomic and honest ---------------------------------------------------------------------------------------------
def test_add_schedule_time_is_one_transaction_and_refuses_a_duplicate_time(monkeypatch):
    from backend.app.services import user_medication_service as svc

    r1 = SimpleNamespace(time_of_day=time(14, 0), days_of_week=None)
    um = SimpleNamespace(id=3, schedules=[r1], updated_at=None)
    db = MagicMock()
    monkeypatch.setattr(svc, "get_user_medication_owned", lambda d, uid, umid: (um, SimpleNamespace(name="X")))
    monkeypatch.setattr(svc, "build_user_medication_out", lambda u, m: {"reminder_times": ["09:00", "14:00"]})
    out = svc.add_schedule_time(db, 1, 3, "09:00", "MO")
    assert out["reminder_times"] == ["09:00", "14:00"] and db.add.call_count == 1 and db.commit.call_count == 1
    with pytest.raises(svc.ScheduleTimeCollisionError):
        svc.add_schedule_time(db, 1, 3, "14:00")
    assert db.commit.call_count == 1


def test_promote_creates_the_pill_with_both_times_and_soft_cancels_the_event_in_one_commit(monkeypatch):
    from backend.app.services import user_medication_service as svc

    ev = SimpleNamespace(id=15, starts_at=datetime(2026, 11, 12, 14, 0), timezone="Asia/Tehran", status="scheduled", valid_to=None,
                         updated_at=None, recurrence_rule="FREQ=DAILY")
    q_event, q_um = MagicMock(), MagicMock()
    q_event.filter.return_value.first.return_value = ev
    q_um.filter.return_value.first.return_value = None
    db = MagicMock()
    db.query.side_effect = [q_event, q_um]
    monkeypatch.setattr(svc, "find_or_create_medication", lambda d, name, **k: SimpleNamespace(id=9, name=name))
    monkeypatch.setattr(svc, "build_user_medication_out", lambda u, m: {"reminder_times": sorted(svc.format_time_of_day(r.time_of_day) for r in u.schedules)})
    added = []
    db.add.side_effect = lambda obj: added.append(obj)
    out = svc.promote_event_to_medication(db, 1, 15, "قرص مکمل", "09:00", "MO,TU")
    assert ev.status == "cancelled" and ev.valid_to is not None  # soft cancel: the row stays
    assert db.commit.call_count == 1  # ONE transaction: never both reminders, never neither
    times = sorted(o.time_of_day for o in added if hasattr(o, "time_of_day"))
    days = {o.time_of_day: o.days_of_week for o in added if hasattr(o, "time_of_day")}
    assert times == [time(9, 0), time(14, 0)] and days == {time(14, 0): None, time(9, 0): "MO,TU"}  # each dose keeps its own weekdays
    with pytest.raises(svc.UserMedicationNotFoundError):
        q_event.filter.return_value.first.return_value = None
        db.query.side_effect = [q_event]
        svc.promote_event_to_medication(db, 1, 99, "X", "09:00")


# --- the title of a plain pill event --------------------------------------------------------------------------------------------------
def test_a_plain_pill_event_gets_a_clean_title(monkeypatch):
    from backend.app.services.intelligence import reminder_event_dispatch as disp

    seen = []
    monkeypatch.setattr(disp, "create_event", lambda db, uid, body: seen.append(body.title) or {"id": 1})
    monkeypatch.setattr(disp, "find_duplicate_conversation_event", lambda db, **k: None)
    res = disp.dispatch_reminder_user_event(
        MagicMock(), user_id=1, message="فردا ساعت ۹ صبح یادم بنداز هم قرصمو بخورم", timezone_name=TZ, now_utc=NOW, language="fa", skip_medication_interview=True
    )
    assert res["created"] and seen and "هم" not in seen[0].split() and "بخورم" not in seen[0]


# --- through the REAL orchestrator --------------------------------------------------------------------------------------------------------
def _orch():
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    called = {"gen": False}

    def gen(*a, **k):
        called["gen"] = True
        return {"message": "GENERIC", "detected_name": None}

    return IntelligenceOrchestrator(db=MagicMock(), legacy_generator=gen, structured_mode=False), called


def test_orchestrator_a_dated_pill_request_asks_once_or_repeating(monkeypatch, world):
    monkeypatch.setattr(mc, "_recent_turns", lambda db, uid, now: [])
    orch, called = _orch()
    out = orch.process(authenticated_user_id=42, message=DAY_REQ, language="fa")
    assert mc._stage_of(out.message, "fa") == "ask_repeat" and world.created == [] and called["gen"] is False


def test_orchestrator_the_repeat_answer_continues_into_the_pill_interview(monkeypatch, world):
    ask = sedi_copy.t("medication.chat.q.ask_repeat", "fa", when="فردا ساعت 09:00")
    monkeypatch.setattr(mc, "_recent_turns", lambda db, uid, now: _rows((DAY_REQ, ask)))
    orch, called = _orch()
    out = orch.process(authenticated_user_id=42, message="هر روز", language="fa")
    assert out.message == sedi_copy.t("medication.chat.q.ask_name", "fa") and called["gen"] is False


# --- Codex round 1 on PR 193 ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "a,b,same",
    [
        ("Vitamin C", "Vitamin D", False), ("Metformin 500 mg", "Metformin 1000 mg", False), ("Metformin 500 mg", "Metformin 500 mg", True),
        ("Metformin", "Metformin 500 mg", True), ("ویتامین C", "ویتامین D", False), ("قرص مکمل", "مکمل", True),
        ("لووتیروکسین", "قرص لووتیروکسین", True), ("Aspirin", "Metformin", False),
    ],
)
def test_p1_the_same_pill_needs_equal_identity_and_strength(a, b, same):
    assert reg.same_pill(a, b) is same


def test_p1_a_different_strength_or_product_is_not_added_as_a_dose(world):
    world.pills = [_pill(name="Metformin 500 mg", times=("08:00",))]
    out = _start("remind me every day at 9 pm to take aspirin pill", "en")
    assert out["interview"] in ("confirm_name", "ask_name") and world.added == [] and world.promoted == []


def test_p1_pick_prefers_the_pill_whose_every_identity_word_is_named():
    pills = [_pill(name="Vitamin C", pid=1), _pill(name="Vitamin D", pid=2)]
    assert reg.pick("vitamin d", pills)["id"] == 2 and reg.pick("vitamin", pills) is None


def test_p1_promotion_keeps_each_dose_with_its_own_weekdays(monkeypatch):
    from backend.app.services import user_medication_service as svc

    ev = SimpleNamespace(id=15, starts_at=datetime(2026, 11, 9, 14, 0), timezone="Asia/Tehran", status="scheduled", valid_to=None,
                         updated_at=None, recurrence_rule="FREQ=WEEKLY;BYDAY=MO")
    q_event, q_um = MagicMock(), MagicMock()
    q_event.filter.return_value.first.return_value = ev
    q_um.filter.return_value.first.return_value = None
    db = MagicMock()
    db.query.side_effect = [q_event, q_um]
    monkeypatch.setattr(svc, "find_or_create_medication", lambda d, name, **k: SimpleNamespace(id=9, name=name))
    monkeypatch.setattr(svc, "build_user_medication_out", lambda u, m: {"reminder_times": []})
    added = []
    db.add.side_effect = lambda obj: added.append(obj)
    svc.promote_event_to_medication(db, 1, 15, "قرص مکمل", "09:00", None)  # the new dose is DAILY, the older one Monday-only
    days = {o.time_of_day: o.days_of_week for o in added if hasattr(o, "time_of_day")}
    assert days == {time(14, 0): "0", time(9, 0): None}


def test_p2_a_confirmed_repeat_survives_the_following_turns(monkeypatch, world):
    ask_rep = sedi_copy.t("medication.chat.q.ask_repeat", "fa", when="فردا ساعت 09:00")
    ask_name = sedi_copy.t("medication.chat.q.ask_name", "fa")
    rows = _rows(("هر روز", ask_name), (DAY_REQ, ask_rep))  # newest first
    reply = _go(monkeypatch, rows, "لووتیروکسین")
    assert reply and "لووتیروکسین" in reply and mc._stage_of(reply, "fa") == "ask_reason"
    rows2 = _rows(("لووتیروکسین", sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین")), ("هر روز", ask_name), (DAY_REQ, ask_rep))
    final = _go(monkeypatch, rows2, "برای تیروئید")
    assert world.created == ["لووتیروکسین"] and final and "09:00" in final


def test_p2_without_the_repeat_answer_a_dated_request_is_still_dropped(monkeypatch, world):
    ask_name = sedi_copy.t("medication.chat.q.ask_name", "fa")
    rows = _rows(("بله", ask_name), (DAY_REQ, ask_name))
    assert _go(monkeypatch, rows, "لووتیروکسین") is None


# --- Codex round 2 on PR 193 ----------------------------------------------------------------------------------------------------------------
def test_p2_an_independent_reminder_request_bypasses_the_promoted_reason_step(monkeypatch, world):
    ask = sedi_copy.t("medication.chat.q.ask_reason_promoted", "fa", name="قرص مکمل", times="09:00، 14:00")
    assert _go(monkeypatch, _rows(("هم", ask)), "فردا ساعت ۱۰ صبح جلسه دارم یادم بنداز") is None  # normal routing handles it


def test_p2_an_older_reminder_with_an_advance_offset_is_never_promoted(monkeypatch):
    from backend.app.services import user_medication_service as svc

    ev = SimpleNamespace(id=15, starts_at=datetime(2026, 11, 12, 14, 0), timezone="Asia/Tehran", status="scheduled", valid_to=None,
                         updated_at=None, recurrence_rule="FREQ=DAILY", reminder_offsets_json="[30]")
    q = MagicMock()
    q.filter.return_value.first.return_value = ev
    db = MagicMock()
    db.query.return_value = q
    with pytest.raises(svc.UserMedicationNotFoundError):
        svc.promote_event_to_medication(db, 1, 15, "قرص مکمل", "09:00")
    assert db.commit.call_count == 0 and ev.status == "scheduled"


def test_p2_the_registry_does_not_offer_an_event_with_a_lead_time(monkeypatch):
    plain = SimpleNamespace(id=1, title="خوردن قرص مکملم", starts_at=datetime(2026, 11, 12, 14, 0), valid_to=None, recurrence_rule="FREQ=DAILY", reminder_offsets_json=None)
    lead = SimpleNamespace(id=2, title="قرص فشار", starts_at=datetime(2026, 11, 12, 20, 0), valid_to=None, recurrence_rule="FREQ=DAILY", reminder_offsets_json="[30]")

    def query(model):
        q = MagicMock()
        name = getattr(model, "__name__", "")
        rows = [plain, lead] if name == "UserEvent" else []
        q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows
        return q

    db = MagicMock()
    db.query.side_effect = query
    pills = reg.existing_pills(db, 1)
    assert [p["id"] for p in pills if p["kind"] == "event"] == [1]


# --- Codex round 3 on PR 193 ----------------------------------------------------------------------------------------------------------------
def test_p1_a_weekly_event_without_byday_keeps_the_weekday_of_its_first_occurrence(monkeypatch):
    from backend.app.services import user_medication_service as svc

    # 2026-11-09 is a Monday -> weekday 0
    assert svc._days_from_rule("FREQ=WEEKLY", datetime(2026, 11, 9, 14, 0)) == "0"
    assert svc._days_from_rule("FREQ=WEEKLY;BYDAY=TU,TH", datetime(2026, 11, 9, 14, 0)) == "1,3"
    assert svc._days_from_rule("FREQ=DAILY", datetime(2026, 11, 9, 14, 0)) is None and svc._days_from_rule(None, None) is None


def test_p1_a_series_that_starts_later_is_not_offered_for_promotion():
    from datetime import timedelta

    today = datetime.utcnow().replace(hour=14, minute=0, second=0, microsecond=0)
    future = SimpleNamespace(id=7, title="قرص مکمل", starts_at=today + timedelta(days=7), timezone="Asia/Tehran", valid_to=None, recurrence_rule="FREQ=DAILY", reminder_offsets_json=None)
    started = SimpleNamespace(id=8, title="قرص مکمل دو", starts_at=today - timedelta(days=7), timezone="Asia/Tehran", valid_to=None, recurrence_rule="FREQ=DAILY", reminder_offsets_json=None)

    def query(model):
        q = MagicMock()
        rows = [future, started] if getattr(model, "__name__", "") == "UserEvent" else []
        q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows
        return q

    db = MagicMock()
    db.query.side_effect = query
    assert [p["id"] for p in reg.existing_pills(db, 1) if p["kind"] == "event"] == [8]


# --- Codex round 4 on PR 193 ----------------------------------------------------------------------------------------------------------------
def _promote_db(monkeypatch, ev, um):
    from backend.app.services import user_medication_service as svc

    q_event, q_um = MagicMock(), MagicMock()
    q_event.filter.return_value.first.return_value = ev
    q_um.filter.return_value.first.return_value = um
    db = MagicMock()
    db.query.side_effect = [q_event, q_um]
    monkeypatch.setattr(svc, "find_or_create_medication", lambda d, name, **k: SimpleNamespace(id=9, name=name))
    monkeypatch.setattr(svc, "build_user_medication_out", lambda u, m: {"reminder_times": []})
    added = []
    db.add.side_effect = lambda obj: added.append(obj)
    return svc, db, added


def _event_obj(rule="FREQ=WEEKLY;BYDAY=MO"):
    return SimpleNamespace(id=15, starts_at=datetime(2026, 11, 9, 14, 0), timezone="Asia/Tehran", status="scheduled", valid_to=None,
                           updated_at=None, recurrence_rule=rule, reminder_offsets_json=None)


def test_p1_a_disabled_medication_is_re_enabled_by_the_promotion(monkeypatch):
    um = SimpleNamespace(id=3, schedules=[], reminder_enabled=False, updated_at=None)
    svc, db, added = _promote_db(monkeypatch, _event_obj(), um)
    svc.promote_event_to_medication(db, 1, 15, "قرص مکمل", "09:00", None)
    assert um.reminder_enabled is True  # the working event is cancelled, so the pill must keep reminding


def test_p2_two_doses_at_the_same_time_merge_their_weekdays(monkeypatch):
    um = SimpleNamespace(id=3, schedules=[], reminder_enabled=True, updated_at=None)
    svc, db, added = _promote_db(monkeypatch, _event_obj("FREQ=WEEKLY;BYDAY=MO"), um)
    svc.promote_event_to_medication(db, 1, 15, "قرص مکمل", "14:00", None)  # the new request: daily 14:00; the older: Monday 14:00
    rows = [o for o in added if hasattr(o, "time_of_day")]
    assert len(rows) == 1 and rows[0].days_of_week is None  # daily wins; nothing is dropped
    um2 = SimpleNamespace(id=3, schedules=[SimpleNamespace(time_of_day=time(14, 0), days_of_week="1")], reminder_enabled=True, updated_at=None)
    svc2, db2, added2 = _promote_db(monkeypatch, _event_obj("FREQ=WEEKLY;BYDAY=MO"), um2)
    svc2.promote_event_to_medication(db2, 1, 15, "قرص مکمل", "09:00", "2")
    assert um2.schedules[0].days_of_week == "0,1"  # Monday (older event) + Tuesday (already there)


def test_p2_merge_days_helper():
    from backend.app.services import user_medication_service as svc

    assert svc._merge_days("0", "3") == "0,3" and svc._merge_days(None, "3") is None and svc._merge_days("2", None) is None


# --- Codex round 5 on PR 193 ----------------------------------------------------------------------------------------------------------------
def _um(rows, tz="Asia/Tehran"):
    return SimpleNamespace(id=3, schedules=rows, updated_at=None, timezone=tz)


def _svc(monkeypatch, um):
    from backend.app.services import user_medication_service as svc

    monkeypatch.setattr(svc, "get_user_medication_owned", lambda d, uid, umid: (um, SimpleNamespace(name="X")))
    monkeypatch.setattr(svc, "build_user_medication_out", lambda u, m: {"reminder_times": []})
    return svc


def test_p2_the_same_time_with_wider_weekdays_merges_instead_of_refusing(monkeypatch):
    row = SimpleNamespace(time_of_day=time(9, 0), days_of_week="0")  # Monday only
    svc = _svc(monkeypatch, _um([row]))
    db = MagicMock()
    svc.add_schedule_time(db, 1, 3, "09:00", None)  # the user now wants it DAILY
    assert row.days_of_week is None and db.commit.call_count == 1 and db.add.call_count == 0
    with pytest.raises(svc.ScheduleTimeCollisionError):  # nothing would change
        svc.add_schedule_time(db, 1, 3, "09:00", None)
    row2 = SimpleNamespace(time_of_day=time(9, 0), days_of_week="0")
    svc2 = _svc(monkeypatch, _um([row2]))
    svc2.add_schedule_time(db, 1, 3, "09:00", "2")
    assert row2.days_of_week == "0,2"


def test_p2_a_time_spoken_in_another_timezone_is_converted_into_the_medicines_own(monkeypatch):
    from backend.app.services import user_medication_service as svc

    # Tehran is UTC+3:30 (no DST since 2022): 09:00 UTC -> 12:30 Tehran
    assert svc.convert_hhmm("09:00", "UTC", "Asia/Tehran") == "12:30"
    assert svc.convert_hhmm("09:00", "Asia/Tehran", "Asia/Tehran") == "09:00" and svc.convert_hhmm("09:00", None, "Asia/Tehran") == "09:00"
    assert svc.convert_hhmm("09:00", "Not/AZone", "Asia/Tehran") == "09:00"  # fail-open: unchanged
    um = _um([SimpleNamespace(time_of_day=time(14, 0), days_of_week=None)], tz="Asia/Tehran")
    added = []
    s = _svc(monkeypatch, um)
    db = MagicMock()
    db.add.side_effect = lambda o: added.append(o)
    s.add_schedule_time(db, 1, 3, "09:00", None, from_tz="UTC")
    assert added and added[0].time_of_day == time(12, 30)


def test_p2_the_request_timezone_reaches_the_owner_write(monkeypatch, world):
    seen = []
    monkeypatch.setattr(reg, "add_dose", lambda db, uid, pill, hhmm, days, from_tz=None: seen.append(from_tz) or [hhmm])
    world.pills = [_pill(name="لووتیروکسین")]
    _start("ساعت ۹ صبح یادم بنداز قرص لووتیروکسین بخورم")
    assert seen == ["Asia/Tehran"]


# --- Codex round 6 on PR 193 ----------------------------------------------------------------------------------------------------------------
def test_p1_a_partly_overlapping_name_never_selects_the_only_pill():
    only_c = [_pill(name="Vitamin C", pid=1)]
    assert reg.pick("Vitamin D", only_c) is None and reg.pick("vitamin d please", only_c) is None
    assert reg.pick("same", only_c)["id"] == 1 and reg.pick("همان", [_pill()])["id"] == 3
    assert reg.pick("same one", only_c)["id"] == 1 and reg.pick("vitamin c", only_c)["id"] == 1


def test_p1_through_the_interview_vitamin_d_does_not_add_a_dose_to_vitamin_c(monkeypatch, world):
    world.pills = [_pill(name="Vitamin C", pid=1)]
    ask = sedi_copy.t("medication.chat.q.ask_same", "en", names="“Vitamin C”")
    rows = _rows(("remind me every day at 9 am to take a pill", ask))
    reply = _go(monkeypatch, rows, "Vitamin D", "en")
    assert world.added == [] and world.promoted == [] and mc._stage_of(reply, "en") == "ask_same"


# --- Codex round 7 on PR 193 ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "answer,expected",
    [
        ("do not repeat", "once"), ("don't repeat it", "once"), ("فقط یک‌بار", "once"), ("تکرار نشود", "once"), ("just once", "once"),
        ("every day", "every"), ("repeat every day", "every"), ("هر روز تکرار شود", "every"), ("repeat", "every"), ("daily", "every"),
        ("repeat weekly", None), ("هر هفته", None), ("maybe", None),
    ],
)
def test_p2_once_or_repeat_answers_are_read_carefully(monkeypatch, world, answer, expected):
    ask = sedi_copy.t("medication.chat.q.ask_repeat", "fa", when="فردا ساعت 09:00")
    reply = _go(monkeypatch, _rows((DAY_REQ, ask)), answer)
    if expected == "once":
        assert reply == "ONCE-EVENT"
    elif expected == "every":
        assert reply == sedi_copy.t("medication.chat.q.ask_name", "fa") and world.once == []
    else:
        assert mc._stage_of(reply, "fa") == "ask_repeat" and world.once == [] and world.created == []


# --- Codex round 8 on PR 193 ----------------------------------------------------------------------------------------------------------------
def test_p2_two_older_reminders_of_one_pill_are_one_pill_and_promoted_together(monkeypatch):
    e1 = SimpleNamespace(id=1, title="خوردن قرص مکملم", starts_at=datetime(2026, 11, 1, 9, 0), valid_to=None, recurrence_rule="FREQ=DAILY", reminder_offsets_json=None, timezone="Asia/Tehran")
    e2 = SimpleNamespace(id=2, title="قرص مکمل بخورم", starts_at=datetime(2026, 11, 1, 14, 0), valid_to=None, recurrence_rule="FREQ=DAILY", reminder_offsets_json=None, timezone="Asia/Tehran")

    def query(model):
        q = MagicMock()
        rows = [e1, e2] if getattr(model, "__name__", "") == "UserEvent" else []
        q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows
        return q

    db = MagicMock()
    db.query.side_effect = query
    pills = [p for p in reg.existing_pills(db, 1) if p["kind"] == "event"]
    assert len(pills) == 1 and pills[0]["ids"] == [1, 2] and pills[0]["times"] == ["09:00", "14:00"]


def test_p2_promotion_cancels_every_older_reminder_of_the_pill_in_one_commit(monkeypatch):
    from backend.app.services import user_medication_service as svc

    e1 = SimpleNamespace(id=1, starts_at=datetime(2026, 11, 1, 9, 0), timezone="Asia/Tehran", status="scheduled", valid_to=None, updated_at=None,
                         recurrence_rule="FREQ=DAILY", reminder_offsets_json=None)
    e2 = SimpleNamespace(id=2, starts_at=datetime(2026, 11, 1, 14, 0), timezone="Asia/Tehran", status="scheduled", valid_to=None, updated_at=None,
                         recurrence_rule="FREQ=WEEKLY;BYDAY=MO", reminder_offsets_json=None)
    q_event, q_um, q_other = MagicMock(), MagicMock(), MagicMock()
    q_event.filter.return_value.first.return_value = e1
    q_um.filter.return_value.first.return_value = None
    q_other.filter.return_value.first.return_value = e2
    db = MagicMock()
    db.query.side_effect = [q_event, q_um, q_other]
    monkeypatch.setattr(svc, "find_or_create_medication", lambda d, name, **k: SimpleNamespace(id=9, name=name))
    monkeypatch.setattr(svc, "build_user_medication_out", lambda u, m: {"reminder_times": []})
    added = []
    db.add.side_effect = lambda o: added.append(o)
    svc.promote_event_to_medication(db, 1, 1, "قرص مکمل", "20:00", None, None, also_event_ids=[2])
    assert e1.status == "cancelled" and e2.status == "cancelled" and db.commit.call_count == 1
    days = {o.time_of_day: o.days_of_week for o in added if hasattr(o, "time_of_day")}
    assert days == {time(9, 0): None, time(14, 0): "0", time(20, 0): None}
