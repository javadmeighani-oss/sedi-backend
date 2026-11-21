"""R-103 / R-088 (Javad's phone test 2026-11-21): «هر روز ساعت ۹ صبح و ۴ عصر یادآوری کنی که قرصمو بخورم» then «همون قرص مکمل است، ساعتشو تغییر بده».

Pilot: Sedi kept the OLD time and ADDED only the first new one («ساعت‌هایش 09:00، 14:00»): the second time («۴ عصر») was silently dropped and
«change its time» was treated as «add a time». Fixed on the real medicine owner: every time the user said is used, and «change» REPLACES.
The scenario runs on a real database session (in-memory SQLite); the medicine owner, the registry and the interview are not stubbed.
"""
from datetime import datetime, timedelta

import pytest
import pytz

from backend.app import models, sedi_copy
from backend.app.services.intelligence import reminder_event_readiness as rer
from backend.app.services.medication_care import chat_reminder as cr
from backend.app.services.medication_care import pill_registry as reg
from backend.tests.test_r108_event_care import db, user  # noqa: F401  (real-session fixtures)

TZ = "Asia/Tehran"
REQUEST = "میخوام هر روز ساعت ۹ صبح و ۴عصر به من یادآوری کنی که قرصمو بخورم"


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    from backend.app.services.gate4 import policy_prefs_bridge

    monkeypatch.setattr(policy_prefs_bridge, "resolve_validated_user_timezone", lambda d, u: TZ)


# --- pure helpers --------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "message,expected",
    [
        (REQUEST, ["09:00", "16:00"]),
        ("9 am and 4 pm every day remind me to take my pill", ["09:00", "16:00"]),
        ("هر روز ساعت ۸ صبح، ساعت ۸ شب قرصمو یادم بنداز", ["08:00", "20:00"]),
        ("هر روز ساعت ۹ صبح یادم بنداز قرصمو بخورم", ["09:00"]),
        ("ساعت ۹ صبح و ساعت ۹ صبح", ["09:00"]),
        ("بدون ساعت", []),
        ("", []),
    ],
)
def test_every_time_the_user_said_is_found_in_order(message, expected):
    assert cr.request_times(message) == expected


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("همون قرص مکمل است ساعتشو تغییر بده", True), ("ساعتش رو عوض کن", True), ("به جای ۱۴ بذار", True),
        ("change its time", True), ("replace the time", True), ("غيّر الوقت", True),
        ("همون قرص است", False), ("اضافه کن", False), ("yes the same one", False),
    ],
)
def test_change_is_told_apart_from_add(answer, expected):
    assert cr.says_change(answer) is expected


def _draft(message=REQUEST):
    draft, missing = rer.parse_reminder_event_draft(message=message, timezone_name=TZ, language="fa")
    assert missing is None
    return draft


def test_dose_times_uses_all_the_times_but_never_overrides_an_explicit_offset():
    assert cr.dose_times(_draft(), REQUEST) == ["09:00", "16:00"]
    assert cr.dose_times(_draft("هر روز ساعت ۹ صبح یادم بنداز قرصمو بخورم"), "هر روز ساعت ۹ صبح یادم بنداز قرصمو بخورم") == ["09:00"]
    offset = _draft("هر روز نیم ساعت قبل از ساعت ۹ صبح یادم بنداز قرصمو بخورم")
    assert cr.dose_times(offset, "هر روز نیم ساعت قبل از ساعت ۹ صبح یادم بنداز قرصمو بخورم") is None  # an advance reminder keeps the event route


# --- the pilot scenario on a real session ---------------------------------------------------------------------------------------------------------
def _old_reminder(db, user, hhmm="14:00", title="قرص مکمل"):
    yesterday = datetime.utcnow() - timedelta(days=2)
    event = models.UserEvent(
        user_id=user.id, title=title, event_type="other", event_domain="personal", timezone=TZ, status="scheduled",
        starts_at=datetime.strptime(yesterday.strftime("%Y-%m-%d ") + hhmm, "%Y-%m-%d %H:%M"), recurrence_rule="FREQ=DAILY",
        reminder_enabled=True, created_at=yesterday,
    )
    db.add(event)
    db.commit()
    return event


def _say(db, user, message, reply):
    from backend.app.core.conversation.memory import ConversationMemory

    assert ConversationMemory(db).save_conversation(user.id, message, reply, "fa") is not None


def _times_of(db, user, name="قرص مکمل"):
    pill = reg.find_registered(db, user.id, name)
    return None if pill is None else pill["times"]


def _first_turn(db, user):
    res = cr.start_interview(db, user_id=user.id, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    assert res and res["interview"] == "ask_same"  # «the older pill, or a new one?»
    question = cr.confirmation(res, "fa", "")
    assert "که از قبل داری" in question
    _say(db, user, REQUEST, question)
    return question


def test_change_its_time_replaces_the_old_time_with_everything_the_user_said(db, user):
    event = _old_reminder(db, user, "14:00")
    _first_turn(db, user)
    reply = cr.continue_interview(db, user_id=user.id, message="همون قرص مکمل است ساعتشو تغییر بده", language="fa", timezone_name=TZ)
    assert _times_of(db, user) == ["09:00", "16:00"]            # the old 14:00 is gone, BOTH new times are set
    assert "09:00" in reply and "16:00" in reply and "14:00" not in reply  # and Sedi says exactly that
    db.refresh(event)
    assert event.status == "cancelled"                           # the older reminder is retired: no double reminder


def test_without_a_change_request_every_new_time_is_added_next_to_the_old_one(db, user):
    _old_reminder(db, user, "14:00")
    _first_turn(db, user)
    reply = cr.continue_interview(db, user_id=user.id, message="همون قرص مکمل است", language="fa", timezone_name=TZ)
    assert _times_of(db, user) == ["09:00", "14:00", "16:00"] and "16:00" in reply  # the second time is no longer lost


def test_a_time_that_already_exists_is_skipped_not_an_error(db, user):
    _old_reminder(db, user, "09:00")
    _first_turn(db, user)
    cr.continue_interview(db, user_id=user.id, message="همون قرص مکمل است", language="fa", timezone_name=TZ)
    assert _times_of(db, user) == ["09:00", "16:00"]  # 09:00 was already there; 16:00 is new


def test_a_registered_pill_gets_replacement_and_additions_too(db, user):
    from backend.app.schemas.medical import UserMedicationCreateIn
    from backend.app.services import user_medication_service as svc

    svc.create_user_medication(db, user.id, UserMedicationCreateIn(name="قرص مکمل", reminder_times=["14:00"], timezone=TZ))
    res = cr.start_interview(db, user_id=user.id, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    _say(db, user, REQUEST, cr.confirmation(res, "fa", ""))
    cr.continue_interview(db, user_id=user.id, message="همون قرص مکمل است ساعتشو عوض کن", language="fa", timezone_name=TZ)
    assert _times_of(db, user) == ["09:00", "16:00"]


def test_the_owner_replaces_in_one_transaction_and_rejects_an_empty_list(db, user):
    from backend.app.schemas.medical import UserMedicationCreateIn
    from backend.app.services import user_medication_service as svc

    out = svc.create_user_medication(db, user.id, UserMedicationCreateIn(name="ویتامین", reminder_times=["08:00", "20:00"], timezone=TZ))
    assert svc.replace_schedule_times(db, user.id, out["id"], ["09:00"], None, TZ)["reminder_times"] == ["09:00"]
    with pytest.raises(ValueError):
        svc.replace_schedule_times(db, user.id, out["id"], [], None, TZ)
    assert svc.list_user_medications(db, user.id)[0]["reminder_times"] == ["09:00"]  # nothing changed by the rejected call


def test_a_new_pill_request_with_two_times_creates_both_doses(db, user):
    """No older pill: the care interview ends with ONE medicine that carries every time the user said."""
    res = cr.start_interview(db, user_id=user.id, message=REQUEST, draft=_draft(), language="fa", timezone_name=TZ)
    assert res["interview"] in ("ask_name", "confirm_name")
    reply = cr.confirmation(res, "fa", "")
    _say(db, user, REQUEST, reply)
    for answer in ("ویتامین دی", "چون کمبود دارم"):  # every turn is stored, as in the real chat, so the next one finds its question
        reply = cr.continue_interview(db, user_id=user.id, message=answer, language="fa", timezone_name=TZ)
        assert reply
        _say(db, user, answer, reply)
    pills = reg.existing_pills(db, user.id)
    assert len(pills) == 1 and pills[0]["kind"] == "med" and pills[0]["times"] == ["09:00", "16:00"]  # both doses exist on the new medicine


# --- Codex round 1 on PR 206 ------------------------------------------------------------------------------------------------------------------
def test_p2_a_conjunction_inside_a_clock_time_is_not_a_separator():
    assert cr.request_times("هر روز ساعت ۸ و نیم شب و ساعت ۱۰ شب یادآوری کن قرصمو بخورم") == ["20:30", "22:00"]
    message = "هر روز ساعت ۸ و نیم شب و ساعت ۱۰ شب یادآوری کن قرصمو بخورم"
    assert cr.dose_times(_draft(message), message) == ["20:30", "22:00"]  # the first dose is not moved twelve hours early


def test_p2_the_several_times_never_override_a_parse_they_disagree_with(monkeypatch):
    draft = _draft("هر روز ساعت ۹ صبح یادم بنداز قرصمو بخورم")
    monkeypatch.setattr(cr, "request_times", lambda message: ["03:00", "05:00"])  # a mis-split that does not contain the parsed 09:00
    assert cr.dose_times(draft, "x") == ["09:00"]


def test_p1_a_weekday_restriction_lands_on_the_replacement_rows(db, user):
    from backend.app.schemas.medical import UserMedicationCreateIn
    from backend.app.services import user_medication_service as svc

    out = svc.create_user_medication(db, user.id, UserMedicationCreateIn(name="قرص هفتگی", reminder_times=["08:00"], timezone=TZ))
    svc.replace_schedule_times(db, user.id, out["id"], ["09:00", "16:00"], "0,3", TZ)
    rows = db.query(models.UserMedicationSchedule).filter(models.UserMedicationSchedule.user_medication_id == out["id"]).all()
    assert sorted(r.time_of_day.strftime("%H:%M") for r in rows) == ["09:00", "16:00"] and {r.days_of_week for r in rows} == {"0,3"}
    svc.replace_schedule_times(db, user.id, out["id"], ["10:00"], None, TZ)  # no restriction: daily again
    rows = db.query(models.UserMedicationSchedule).filter(models.UserMedicationSchedule.user_medication_id == out["id"]).all()
    assert [r.time_of_day.strftime("%H:%M") for r in rows] == ["10:00"] and rows[0].days_of_week is None


def test_p1_a_weekly_pill_change_keeps_its_days(db, user):
    """A weekly request that reaches the same-pill action (a series that already started) keeps its weekday on every replaced dose."""
    from backend.app.schemas.medical import UserMedicationCreateIn
    from backend.app.services import user_medication_service as svc

    msg = "هر دوشنبه ساعت ۹ صبح و ۴ عصر قرصمو یادم بنداز"
    svc.create_user_medication(db, user.id, UserMedicationCreateIn(name="قرص مکمل", reminder_times=["14:00"], timezone=TZ))
    pill = reg.find_registered(db, user.id, "قرص مکمل")
    out = cr._same_action(db, user_id=user.id, pill=pill, draft=_draft(msg), lang="fa", message=msg, replace=True)
    assert out and out["flow"] == "dose_added" and out["times"] == "09:00، 16:00"
    rows = db.query(models.UserMedicationSchedule).all()
    assert sorted(r.time_of_day.strftime("%H:%M") for r in rows) == ["09:00", "16:00"] and {r.days_of_week for r in rows} == {"0"}  # Monday only


def test_p2_a_mixed_morning_evening_sentence_the_parser_reads_as_one_period_still_gives_both_doses():
    message = "هر دوشنبه ساعت ۹ صبح و ۴ عصر قرصمو یادم بنداز"
    draft = _draft(message)
    assert draft.starts_at_local.strftime("%H:%M") == "21:00"  # the parser's single period misreads the sentence ...
    assert cr.dose_times(draft, message) == ["09:00", "16:00"]  # ... the per-time reading is what the user said
