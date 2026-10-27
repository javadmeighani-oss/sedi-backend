"""R-031 (2026-10-27): what the user did is memory.

Marking an item done in My Schedule goes through its OWNER (medication dose occurrence / UserEvent) and the I7 "user did
it" ledger; I7 daily signals, reminders and Sedi's chat context READ that ledger.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time as dtime, timedelta
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.core.security import create_access_token
from backend.app.services.i7 import user_done
from backend.app.services.i7.derived_signals import collect_daily_signals, merge_signals
from backend.app.services.section10.event_reminder_scheduler import process_event_reminders
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

TODAY = date(2026, 10, 27)


def _auth(u):
    return {"Authorization": f"Bearer {create_access_token({'user_id': u.id})}"}


def _event(db, u, *, title="جلسه", etype="work_meeting", edomain="work", rule=None, starts=None):
    row = models.UserEvent(
        user_id=u.id,
        title=title,
        event_type=etype,
        event_domain=edomain,
        starts_at=starts or datetime(2026, 10, 27, 10, 30),
        timezone="Asia/Tehran",
        status="scheduled",
        reminder_enabled=True,
        reminder_offsets_json=json.dumps([0]),
        recurrence_rule=rule,
        source="conversation",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _medication(db, u, hhmm="08:00"):
    med = models.Medication(name="TestMed")
    db.add(med)
    db.commit()
    db.refresh(med)
    um = models.UserMedication(user_id=u.id, medication_id=med.id, reminder_enabled=True, timezone="Asia/Tehran")
    db.add(um)
    db.commit()
    db.refresh(um)
    h, m = (int(x) for x in hhmm.split(":"))
    sched = models.UserMedicationSchedule(user_medication_id=um.id, time_of_day=dtime(h, m))
    db.add(sched)
    db.commit()
    return um, sched


# ---------------------------------------------------------------- pure ledger rules
def test_domains_are_coarse_and_never_carry_titles():
    assert user_done.domain_for("medication") == "medication"
    assert user_done.domain_for("event", "doctor_visit", "medical") == "appointment"
    assert user_done.domain_for("event", "lab_test", None) == "appointment"
    assert user_done.domain_for("event", "work_meeting", "work") == "meeting"
    assert user_done.domain_for("event", "other", "lifestyle") == "other"
    assert user_done.occurrence_id("event", 12, TODAY) == "event:12:20261027"
    assert user_done.occurrence_id("medication", 5, TODAY, "08:00") == "medication:5:20261027:0800"


def test_done_then_undo_is_the_latest_state_wins(db):
    u = _user(db, "+17770041001", tz="Asia/Tehran")
    occ = user_done.occurrence_id("event", 1, TODAY)
    assert user_done.is_done(db, u.id, occ) is False
    user_done.record(db, u.id, kind="event", ref_id=1, day=TODAY, hhmm=None, domain="meeting", done=True)
    db.commit()
    assert user_done.is_done(db, u.id, occ) is True
    user_done.record(db, u.id, kind="event", ref_id=1, day=TODAY, hhmm=None, domain="meeting", done=True)  # idempotent
    db.commit()
    assert db.query(models.InteractionEvent).filter(models.InteractionEvent.user_id == u.id).count() == 1
    user_done.record(db, u.id, kind="event", ref_id=1, day=TODAY, hhmm=None, domain="meeting", done=False)
    db.commit()
    assert user_done.is_done(db, u.id, occ) is False
    assert user_done.done_counts_for_day(db, u.id, TODAY) == {}


def test_counts_per_domain_and_merge_into_longer_periods(db):
    u = _user(db, "+17770041002", tz="Asia/Tehran")
    for ref, dom in ((1, "medication"), (2, "medication"), (3, "appointment")):
        user_done.record(db, u.id, kind="event", ref_id=ref, day=TODAY, hhmm=None, domain=dom, done=True)
    db.commit()
    day = user_done.done_counts_for_day(db, u.id, TODAY)
    assert day == {"medication": 2, "appointment": 1}
    assert user_done.done_counts_for_day(db, u.id, TODAY + timedelta(days=1)) == {}
    sig = collect_daily_signals(db, u.id, TODAY, [])
    assert sig["user_done"] == {"medication": 2, "appointment": 1}
    merged = merge_signals([sig, {"user_done": {"medication": 1, "meeting": 3}}])
    assert merged["user_done"] == {"medication": 3, "appointment": 1, "meeting": 3}


def test_no_done_means_signals_are_unchanged(db):
    u = _user(db, "+17770041003", tz="Asia/Tehran")
    assert "user_done" not in collect_daily_signals(db, u.id, TODAY, [])


def test_chat_hint_names_domains_only(db):
    u = _user(db, "+17770041004", tz="Asia/Tehran")
    user_done.record(db, u.id, kind="medication", ref_id=7, day=TODAY, hhmm="08:00", domain="medication", done=True)
    db.commit()
    fa = user_done.done_today_hint(db, u.id, "fa", TODAY)
    assert "دارو" in fa and "[کارهای_انجام‌شده_امروز]" in fa
    en = user_done.done_today_hint(db, u.id, "en", TODAY)
    assert "medication" in en and "[DONE_TODAY]" in en
    assert user_done.done_today_hint(db, u.id, "fa", TODAY + timedelta(days=1)) == ""


# ---------------------------------------------------------------- API through the owners
def test_mark_event_done_completes_a_one_off_and_undo_restores(client, db):
    u = _user(db, "+17770041005", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    ev = _event(db, u, etype="doctor_visit", edomain="medical", title="نوبت دکتر")
    r = client.post("/user/schedule/done", json={"kind": "event", "id": ev.id}, headers=_auth(u))
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["done"] is True and data["domain"] == "appointment" and data["in_memory"] is True
    db.refresh(ev)
    assert ev.status == "completed"
    g = client.get("/user/schedule/done", params={"day": "2026-10-27"}, headers=_auth(u)).json()["data"]
    assert [i["domain"] for i in g["items"]] == ["appointment"]
    r = client.post("/user/schedule/done", json={"kind": "event", "id": ev.id, "done": False}, headers=_auth(u))
    assert r.json()["data"]["done"] is False
    db.refresh(ev)
    assert ev.status == "scheduled"
    assert client.get("/user/schedule/done", params={"day": "2026-10-27"}, headers=_auth(u)).json()["data"]["items"] == []


def test_without_memory_consent_the_mark_still_works_but_is_not_flagged_as_remembered(client, db):
    u = _user(db, "+17770041006", tz="Asia/Tehran")  # no consent
    ev = _event(db, u)
    r = client.post("/user/schedule/done", json={"kind": "event", "id": ev.id}, headers=_auth(u))
    assert r.status_code == 200 and r.json()["data"]["in_memory"] is False


def test_repeating_event_keeps_its_series_and_is_recorded_per_occurrence(client, db):
    u = _user(db, "+17770041007", tz="Asia/Tehran")
    ev = _event(db, u, title="آب", etype="other", edomain="lifestyle", rule="FREQ=DAILY", starts=datetime(2026, 10, 20, 8, 0))
    r = client.post(
        "/user/schedule/done", json={"kind": "event", "id": ev.id, "day": "2026-10-27"}, headers=_auth(u)
    )
    assert r.status_code == 200
    db.refresh(ev)
    assert ev.status == "scheduled"  # the series is NOT completed
    assert user_done.is_event_occurrence_done(db, u.id, ev.id, date(2026, 10, 27)) is True
    assert user_done.is_event_occurrence_done(db, u.id, ev.id, date(2026, 10, 28)) is False


def test_mark_medication_confirms_the_dose_occurrence_so_it_is_not_reminded_again(client, db):
    from backend.app.services.i10.medication_adherence import (
        MedicationAdherenceState,
        occurrence_blocks_reminder,
    )

    u = _user(db, "+17770041008", tz="Asia/Tehran")
    _seed_consent(db, u.id)
    um, sched = _medication(db, u, "08:00")
    r = client.post(
        "/user/schedule/done",
        json={"kind": "medication", "id": um.id, "day": "2026-10-27", "time": "08:00"},
        headers=_auth(u),
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["domain"] == "medication"
    occ = db.query(models.MedicationDoseOccurrence).filter(models.MedicationDoseOccurrence.user_id == u.id).one()
    assert occ.state == MedicationAdherenceState.CONFIRMED_TAKEN.value
    assert occ.confirmation_source == "USER_SCHEDULE_UI" and occ.confirmed_at is not None
    assert occurrence_blocks_reminder(occ) is True
    # undo returns the dose to DUE
    client.post(
        "/user/schedule/done",
        json={"kind": "medication", "id": um.id, "day": "2026-10-27", "time": "08:00", "done": False},
        headers=_auth(u),
    )
    db.refresh(occ)
    assert occ.state == MedicationAdherenceState.DUE.value and occ.confirmed_at is None


def test_validation_and_ownership(client, db):
    a = _user(db, "+17770041009", tz="Asia/Tehran")
    b = _user(db, "+17770041010", tz="Asia/Tehran")
    ev = _event(db, a)
    assert client.post("/user/schedule/done", json={"kind": "event", "id": ev.id}, headers=_auth(b)).status_code == 404
    um, _ = _medication(db, a)
    assert (
        client.post("/user/schedule/done", json={"kind": "medication", "id": um.id}, headers=_auth(a)).status_code == 422
    )  # a medication dose needs its time
    assert client.post("/user/schedule/done", json={"kind": "event", "id": ev.id, "x": 1}, headers=_auth(a)).status_code == 422
    assert client.post("/user/schedule/done", json={"kind": "event", "id": ev.id}).status_code in (401, 403)


# ---------------------------------------------------------------- reminders read the ledger
_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)
_FLAG_PATCH = patch(
    "backend.app.services.section10.feature_flags.event_reminder_scheduler_enabled",
    return_value=True,
)


def test_a_repeating_occurrence_that_is_done_is_not_reminded(db):
    u = _user(db, "+17770041011", tz="Asia/Tehran")
    ensure_self_subject_for_account(db, u.id, commit=True)
    ev = _event(db, u, title="آب بخورم", etype="other", edomain="lifestyle", rule="FREQ=DAILY", starts=datetime(2026, 10, 20, 8, 0))
    user_done.record(db, u.id, kind="event", ref_id=ev.id, day=date(2026, 10, 28), hhmm=None, domain="other", done=True)
    db.commit()
    with _GATE4_PATCH, _FLAG_PATCH:
        # 08:01 Tehran on the 28th = 04:31 UTC: done -> nothing
        assert process_event_reminders(db, now=datetime(2026, 10, 28, 4, 31)) == 0
        # the 29th is not done -> reminded
        assert process_event_reminders(db, now=datetime(2026, 10, 29, 4, 31)) == 1
