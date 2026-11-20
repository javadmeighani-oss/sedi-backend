"""R-108 / R-092 partial lift (Javad 2026-11-20): the care-appointment messages - day-of 09:00 and the check-in two hours before.

Unit level (pure due-time rules) + a real-session loop (in-memory SQLite): sweep -> task -> send guard -> exact copy -> moved / cancelled event.
Kinds: doctor visit, lab test, imaging, surgery and PHYSIOTHERAPY.
"""
import contextlib
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from backend.app import models, sedi_copy


@compiles(BigInteger, "sqlite")
def _sqlite_bigint_is_integer(type_, compiler, **kw):  # SQLite autoincrements only «INTEGER PRIMARY KEY»
    return "INTEGER"
from backend.app.database import Base
from backend.app.services.i10 import event_care as ec
from backend.app.services.i6 import consent_service as consent
from backend.tests.test_r108_care_loop_e2e import TABLES as _LOOP_TABLES

TABLES = _LOOP_TABLES + ("notification_feedback", "notification_guard_state", "notification_prefs", "i10_notification_decisions")

TEHRAN = pytz.timezone("Asia/Tehran")
DAY = "2026-11-24"


def _utc(local: str) -> datetime:
    """«YYYY-MM-DD HH:MM» in Tehran -> naive UTC."""
    return TEHRAN.localize(datetime.strptime(local, "%Y-%m-%d %H:%M")).astimezone(pytz.UTC).replace(tzinfo=None)


def _event(hhmm, *, created="2026-11-22 10:00", offsets=None, etype="physiotherapy", **kw):
    return SimpleNamespace(
        starts_at=datetime.strptime(f"{DAY} {hhmm}", "%Y-%m-%d %H:%M"), timezone="Asia/Tehran", event_type=etype, recurrence_rule=None,
        reminder_enabled=bool(offsets), reminder_offsets_json=None if offsets is None else str(list(offsets)),
        created_at=_utc(created), title="فیزیوتراپی زانو", location=kw.get("location"), status="scheduled",
    )


def _hhmm(utc):
    return None if utc is None else pytz.UTC.localize(utc).astimezone(TEHRAN).strftime("%H:%M")


def _times(event, created_before=True):
    return {k: _hhmm(v) for k, v in ec.due_times(event, TEHRAN, created_before_day_of=created_before).items()}


# --- the kinds -----------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("etype", ["doctor_visit", "lab_test", "imaging", "surgery", "physiotherapy"])
def test_the_care_kinds_include_physiotherapy(etype):
    assert ec.is_care_event(_event("15:00", etype=etype))


@pytest.mark.parametrize("etype", ["work_meeting", "exam", "deadline", "birthday", "other", "nursing_visit"])
def test_other_events_are_not_care_appointments(etype):
    assert not ec.is_care_event(_event("15:00", etype=etype))


def test_a_recurring_event_is_never_a_care_appointment_here():
    event = _event("15:00")
    event.recurrence_rule = "FREQ=WEEKLY"
    assert not ec.is_care_event(event)


# --- when each message goes out ------------------------------------------------------------------------------------------------------------------
def test_an_afternoon_event_gets_the_day_of_message_at_nine_and_the_check_in_two_hours_before():
    assert _times(_event("15:00")) == {ec.KIND_DAY_OF: "09:00", ec.KIND_PRE: "13:00"}
    assert _times(_event("23:00")) == {ec.KIND_DAY_OF: "09:00", ec.KIND_PRE: "21:00"}


def test_a_morning_event_gets_only_the_check_in_and_never_before_seven():  # Javad: before 10:00 -> only the pre-check
    assert _times(_event("11:00")) == {ec.KIND_PRE: "09:00"}
    assert _times(_event("09:30")) == {ec.KIND_PRE: "07:30"}
    assert _times(_event("08:00")) == {ec.KIND_PRE: "07:00"}  # 06:00 would be quiet hours: it moves to 07:00
    assert _times(_event("07:15")) == {}                     # nothing useful fits before such an early start
    assert _times(_event("00:30")) == {}


def test_a_same_morning_booking_gets_no_day_of_message():
    assert _times(_event("15:00", created="2026-11-24 09:30"), created_before=False) == {ec.KIND_PRE: "13:00"}


def test_the_users_own_reminder_about_two_hours_before_replaces_the_check_in():
    assert _times(_event("15:00", offsets=[120])) == {ec.KIND_DAY_OF: "09:00"}
    assert _times(_event("15:00", offsets=[30])) == {ec.KIND_DAY_OF: "09:00", ec.KIND_PRE: "13:00"}  # a different reminder is no duplicate


def test_the_physiotherapy_example_of_javad():
    assert _times(_event("14:00", etype="physiotherapy")) == {ec.KIND_DAY_OF: "09:00", ec.KIND_PRE: "12:00"}


def test_the_feature_is_off_by_default(monkeypatch):
    monkeypatch.delenv(ec.FLAG, raising=False)
    assert ec.enabled() is False and ec.create_due_event_care_tasks(None) == 0
    monkeypatch.setenv(ec.FLAG, "1")
    assert ec.enabled() is True


# --- the real session ------------------------------------------------------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    from backend.app.services.gate4 import policy_prefs_bridge

    monkeypatch.setattr(policy_prefs_bridge, "resolve_validated_user_timezone", lambda db, uid: "Asia/Tehran")
    monkeypatch.setenv(ec.FLAG, "1")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for table in Base.metadata.sorted_tables:  # every table SQLite can hold (a few PostgreSQL-only constraints are skipped)
        try:
            table.create(engine, checkfirst=True)
        except Exception:  # noqa: BLE001
            pass
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.begin_nested = lambda: contextlib.nullcontext()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def user(db):
    row = models.User(name="سارا", secret_key="x", preferred_language="fa")
    db.add(row)
    db.commit()
    consent.grant_memory_consent(db, row.id)
    return row


def _add_event(db, user, hhmm="15:00", etype="physiotherapy", created="2026-11-22 10:00", **kw):
    ev = models.UserEvent(
        user_id=user.id, title=kw.get("title", "فیزیوتراپی زانو"), event_type=etype, event_domain="medical", timezone="Asia/Tehran",
        starts_at=datetime.strptime(f"{DAY} {hhmm}", "%Y-%m-%d %H:%M"), status="scheduled", location=kw.get("location"),
        created_at=_utc(created),
    )
    db.add(ev)
    db.commit()
    return ev


def _tasks(db):
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

    return sorted(
        [(parse_bounded_meta(t.description)[1].follow_up_kind, t) for t in db.query(models.CareFollowUpTask).all()], key=lambda x: x[0]
    )


def test_the_sweep_creates_each_message_just_in_time_and_only_once(db, user):
    _add_event(db, user)
    assert ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 08:00")) == 0      # too early: nothing is created ahead of time
    assert ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 08:50")) == 1      # 10 min before 09:00
    assert ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 09:05")) == 0      # no second day-of task
    assert ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 12:50")) == 1      # the check-in
    assert [k for k, _t in _tasks(db)] == [ec.KIND_DAY_OF, ec.KIND_PRE]
    assert [_hhmm(t.due_at) for _k, t in _tasks(db)] == ["09:00", "13:00"]


def test_no_memory_consent_no_task(db):
    other = models.User(name="بی‌رضایت", secret_key="x", preferred_language="fa")
    db.add(other)
    db.commit()
    _add_event(db, other)
    assert ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 08:55")) == 0


def test_the_message_names_the_appointment_exactly_with_its_time_and_place(db, user):
    from backend.app.services.i10.contextual_followup_i10_adapter import render_followup_copy

    _add_event(db, user, title="فیزیوتراپی زانو، دکتر رضایی", location="کلینیک مهر")
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 08:55"))
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 12:55"))
    copy = {k: render_followup_copy(db, t) for k, t in _tasks(db)}
    title, body, key = copy[ec.KIND_DAY_OF]
    assert key == ec.KIND_DAY_OF and "فیزیوتراپی زانو، دکتر رضایی" in body and "کلینیک مهر" in body and "سارا جان" in body
    assert "09" not in body and ("14" in body or "۱۴" in body or "15" in body or "۱۵" in body)  # the appointment time, not the send time
    title, body, key = copy[ec.KIND_PRE]
    assert key == ec.KIND_PRE and "آماده‌ای؟" in body and "حالت چطور است؟" in body and title == sedi_copy.t("event_care.title.pre", "fa")


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_copy_exists_in_every_language(lang):
    for which in ("day_of", "pre"):
        text = sedi_copy.t(f"event_care.body.{which}", lang, who="", time="15:00", title="X", place=sedi_copy.t("event_care.place", lang, location="Y"))
        assert "{" not in text and "X" in text and "15:00" in text and "Y" in text
        assert sedi_copy.t(f"event_care.title.{which}", lang)


def test_a_moved_or_cancelled_event_drops_the_stale_task(db, user):
    ev = _add_event(db, user)
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 08:55"))
    task = _tasks(db)[0][1]
    assert ec.may_send(db, task, _utc(f"{DAY} 09:00")) is True  # the real send guard (quiet hours, cap, dedup) lets it through
    ev.starts_at = ev.starts_at + timedelta(hours=3)  # moved to 18:00: 09:00 is still the day-of time, but the PRE time changes
    db.commit()
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 12:55"))
    assert [t for k, t in _tasks(db) if k == ec.KIND_PRE] == []  # nothing at 13:00 for an 18:00 event (its check-in is due at 16:00)
    ev.starts_at = ev.starts_at - timedelta(hours=3)
    ev.status = "cancelled"
    db.commit()
    assert ec.may_send(db, task, _utc(f"{DAY} 09:01")) is False and task.status == "cancelled"


def test_a_late_message_is_dropped_not_sent(db, user):
    _add_event(db, user)
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 08:55"))
    task = _tasks(db)[0][1]
    assert ec.may_send(db, task, _utc(f"{DAY} 11:30")) is False and task.status == "cancelled"  # more than 2 h after 09:00


def test_the_worker_dispatch_knows_the_new_kinds(db, user):
    from backend.app.services.i10 import contextual_followup_worker as worker

    _add_event(db, user)
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 08:55"))
    assert worker._is_event_care(_tasks(db)[0][1]) is True


def test_a_check_in_task_made_before_the_event_moved_is_dropped(db, user):
    ev = _add_event(db, user)
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 12:55"))
    pre = [t for k, t in _tasks(db) if k == ec.KIND_PRE][0]
    ev.starts_at = ev.starts_at + timedelta(hours=3)  # 15:00 -> 18:00: «in two hours» at 13:00 would be false
    db.commit()
    assert ec.may_send(db, pre, _utc(f"{DAY} 13:00")) is False and pre.status == "cancelled"




def test_the_worker_really_sends_the_named_messages_once_each(db, user, monkeypatch):
    """End to end on the real I10 rails: sweep -> task -> worker -> send guard -> I10 decision -> notification, no resend."""
    from backend.app.services.i10 import contextual_followup_worker as worker

    monkeypatch.setenv("SEDI_I10_CONTEXTUAL_FOLLOWUP_ENABLED", "1")
    _add_event(db, user, title="فیزیوتراپی زانو", location="کلینیک مهر")
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 08:55"))
    day_of = [t for k, t in _tasks(db) if k == ec.KIND_DAY_OF][0]
    assert worker.process_single_follow_up_task(db, day_of, now=_utc(f"{DAY} 09:00")) is True and day_of.status == "notified"
    sent = db.query(models.Notification).all()
    assert [(n.title, n.body) for n in sent] == [("نوبت امروز", "سارا جان، امروز ساعت 15:00 «فیزیوتراپی زانو» در کلینیک مهر داری")]
    assert sent[0].template_key == ec.KIND_DAY_OF and sent[0].source_id == str(day_of.id)
    assert worker.process_single_follow_up_task(db, day_of, now=_utc(f"{DAY} 09:10")) is False  # no resend
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} 12:55"))
    pre = [t for k, t in _tasks(db) if k == ec.KIND_PRE][0]
    assert worker.process_single_follow_up_task(db, pre, now=_utc(f"{DAY} 13:00")) is True
    bodies = [n.body for n in db.query(models.Notification).order_by(models.Notification.id).all()]
    assert bodies[1] == "سارا جان، ساعت 15:00 «فیزیوتراپی زانو» در کلینیک مهر داری. آماده‌ای؟ حالت چطور است؟"


def test_the_sweep_runs_inside_the_ordinary_worker_tick(db, user, monkeypatch):
    from backend.app.services.i10 import contextual_followup_worker as worker

    monkeypatch.setenv("SEDI_I10_CONTEXTUAL_FOLLOWUP_ENABLED", "1")
    _add_event(db, user)
    assert worker.process_due_follow_up_tasks(db, now=_utc(f"{DAY} 09:00")) == 1  # the tick creates the 09:00 task and sends it
    assert [k for k, _t in _tasks(db)] == [ec.KIND_DAY_OF] and db.query(models.Notification).count() == 1
