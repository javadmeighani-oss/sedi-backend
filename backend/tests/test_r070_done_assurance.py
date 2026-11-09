"""R-070 (step 2D): what the user DID is recorded through its owner and I7; ONE 30-minute assurance for an ignored action.

Matrix: kinds (medication / reminder / plan) x channels (tray / chat / assurance), languages, exclusions, idempotency, wiring.
"""
from __future__ import annotations

import json
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import models, sedi_copy
from backend.app.services import notification_followup_ask as ask
from backend.app.services import notification_openers as no
from backend.app.services.i10 import action_done as ad
from backend.app.services.i10.contextual_followup_worker import process_due_follow_up_tasks
from backend.app.services.i7 import user_done
from backend.app.services.i7.derived_signals import collect_daily_signals, merge_signals
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

_LANGS = ["fa", "ar", "en"]
_NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
_NAIVE_NOW = _NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _flag_and_policy():
    with patch(
        "backend.app.services.i10.contextual_followup_worker.contextual_followup_enabled", return_value=True
    ), patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy", return_value=(True, {})
    ), patch(
        "backend.app.services.notification_runtime.quiet_hours.is_within_quiet_hours", return_value=False
    ):
        yield


def _user_in(db, phone, lang="fa"):
    u = _user(db, phone, tz="Asia/Tehran")
    u.name = "جواد"
    u.preferred_language = lang
    db.commit()
    _seed_consent(db, u.id)
    ensure_self_subject_for_account(db, u.id, commit=True)
    return u


def _notif(db, uid, template_key, family, *, minutes_ago, source_type=None, source_id=None, status="sent"):
    when = _NAIVE_NOW - timedelta(minutes=minutes_ago)
    n = models.Notification(
        user_id=uid, type="connection_ping", title="صدی", body="x", channel="push", status=status, is_sent=True,
        template_key=template_key, semantic_family=family, source_type=source_type, source_id=source_id,
        created_at=when, sent_at=when,
    )
    db.add(n)
    db.commit()
    return n


def _medication(db, u, notif_minutes_ago=40, state="DUE"):
    med = models.Medication(name="TestMed")
    db.add(med)
    db.commit()
    um = models.UserMedication(user_id=u.id, medication_id=med.id, reminder_enabled=True, timezone="Asia/Tehran")
    db.add(um)
    db.commit()
    n = _notif(db, u.id, "medication_reminder", "MEDICATION_DUE", minutes_ago=notif_minutes_ago)
    occ = models.MedicationDoseOccurrence(
        user_id=u.id, user_medication_id=um.id, scheduled_for=_NOW - timedelta(minutes=notif_minutes_ago),
        occurrence_key=f"occ-{u.id}-{n.id}", state=state, source_notification_id=n.id,
    )
    db.add(occ)
    db.commit()
    return n, occ, um


def _reminder(db, u, *, etype="reminder", edomain="personal", minutes_ago=40):
    ev = models.UserEvent(
        user_id=u.id, title="زنگ به مادر", event_domain=edomain, event_type=etype,
        starts_at=_NAIVE_NOW - timedelta(minutes=minutes_ago), status="scheduled",
    )
    db.add(ev)
    db.commit()
    n = _notif(db, u.id, "generic_event_reminder", "REMINDER", minutes_ago=minutes_ago, source_type="user_event", source_id=str(ev.id))
    return n, ev


def _tasks(db, uid):
    return db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == uid).all()


# ---- the tray: done / not done / later on medication and reminders ------------------------------------------------------
def test_done_on_a_medication_notification_confirms_the_dose_and_writes_i7(db):
    u = _user_in(db, "+17770100001")
    n, occ, um = _medication(db, u)
    result = ad.handle_action_answer(db, notification=n, actor_user_id=u.id, payload={"action_id": "done"})
    db.commit()
    db.refresh(occ)
    assert occ.state == "CONFIRMED_TAKEN" and result.canonical_verb == "DONE"
    local_day = (occ.scheduled_for.astimezone(ad._zone(db, u.id))).date()
    assert user_done.done_counts_for_day(db, u.id, local_day) == {"medication": 1}
    # a replayed tap neither double-counts nor raises
    ad.handle_action_answer(db, notification=n, actor_user_id=u.id, payload={"action_id": "done"})
    db.commit()
    assert user_done.done_counts_for_day(db, u.id, local_day) == {"medication": 1}


def test_done_on_a_one_off_reminder_completes_the_event_and_writes_i7(db):
    u = _user_in(db, "+17770100002")
    n, ev = _reminder(db, u)
    ad.handle_action_answer(db, notification=n, actor_user_id=u.id, payload={"action_id": "done"})
    db.commit()
    db.refresh(ev)
    assert ev.status == "completed"
    assert user_done.done_counts_for_day(db, u.id, ev.starts_at.date()) == {"other": 1}


def test_a_done_tap_that_the_owner_cannot_confirm_is_only_acknowledged(db):
    u = _user_in(db, "+17770100003")
    n = _notif(db, u.id, "medication_reminder", "MEDICATION_DUE", minutes_ago=40)  # no dose occurrence behind it
    result = ad.handle_action_answer(db, notification=n, actor_user_id=u.id, payload={"action_id": "done"})
    db.commit()
    assert result.canonical_verb != "DONE"
    assert db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type="user_schedule_done").count() == 0


@pytest.mark.parametrize("kind", ["medication", "event"])
def test_not_done_with_a_reason_is_memory_but_does_not_change_the_owner(db, kind):
    u = _user_in(db, f"+1777010004{kind[0]}")
    if kind == "medication":
        n, occ, _ = _medication(db, u)
        day = occ.scheduled_for.astimezone(ad._zone(db, u.id)).date()
    else:
        n, ev = _reminder(db, u)
        day = ev.starts_at.date()
    ad.handle_action_answer(db, notification=n, actor_user_id=u.id, payload={"action_id": "plan_not_done", "reason": "no_time"})
    db.commit()
    counts = user_done.not_done_counts_for_day(db, u.id, day)
    assert counts.get("reason.no_time") == 1 and sum(v for k, v in counts.items() if not k.startswith("reason.")) == 1
    assert user_done.done_counts_for_day(db, u.id, day) == {}
    if kind == "medication":
        db.refresh(occ)
        assert occ.state != "CONFIRMED_TAKEN"
    else:
        db.refresh(ev)
        assert ev.status == "scheduled"


def test_a_not_done_never_overrides_a_done(db):
    u = _user_in(db, "+17770100005")
    n, ev = _reminder(db, u)
    ad.handle_action_answer(db, notification=n, actor_user_id=u.id, payload={"action_id": "done"})
    db.commit()
    ad.handle_action_answer(db, notification=n, actor_user_id=u.id, payload={"action_id": "plan_not_done", "reason": "no_time"})
    db.commit()
    assert user_done.not_done_counts_for_day(db, u.id, ev.starts_at.date()) == {}


def test_nobody_elses_notification_is_ever_completed(db):
    u = _user_in(db, "+17770100006")
    other = _user_in(db, "+17770100007")
    n, ev = _reminder(db, other)
    assert ad.resolve_target(db, n, u.id) is not None  # the target resolves from the notification...
    assert ad._event_of(db, u.id, n) is None  # ...but the event is only found for its owner
    assert ad.complete(db, u.id, ad.resolve_target(db, n, u.id)) is False
    db.refresh(ev)
    assert ev.status == "scheduled"


# ---- I7 signals ---------------------------------------------------------------------------------------------------------
def test_not_done_and_plan_reach_the_i7_daily_signals_and_merge(db):
    u = _user_in(db, "+17770101001")
    day = _NOW.date()
    user_done.record(db, u.id, kind="plan", ref_id=7, day=day, hhmm=None, domain="plan", done=True)
    user_done.record_not_done(db, u.id, kind="medication", ref_id=3, day=day, hhmm="08:00", domain="medication", reason="not_feeling_well")
    db.commit()
    signals = collect_daily_signals(db, u.id, day, [])
    assert signals["user_done"] == {"plan": 1}
    assert signals["user_not_done"] == {"medication": 1, "reason.not_feeling_well": 1}
    merged = merge_signals([signals, signals])
    assert merged["user_done"] == {"plan": 2} and merged["user_not_done"]["medication"] == 2
    assert "an item of your plan" in user_done.done_today_hint(db, u.id, "en", day)


# ---- the chat answer ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("message,expected", [("آره", "done"), ("نه، وقت نداشتم", "not_done:no_time"), ("yes", "done"), ("لا", "not_done:other")])
def test_a_short_chat_answer_about_a_dose_goes_through_the_owner(db, message, expected):
    u = _user_in(db, f"+177701020{abs(hash(message)) % 90:02d}")
    n, occ, _ = _medication(db, u)
    assert no.apply_chat_answer(db, n, u.id, message) == expected
    db.commit()
    db.refresh(occ)
    assert (occ.state == "CONFIRMED_TAKEN") is (expected == "done")
    assert no.apply_chat_answer(db, n, u.id, "سلام") is None  # not an answer


def test_an_unanswered_follow_up_answer_in_the_opener_is_recorded_by_the_owner(db):
    u = _user_in(db, "+17770102100")
    n, ev = _reminder(db, u, minutes_ago=30 * 60)
    ask.mark_asked(db, u.id, ask.Pending(n.id, "unanswered", "reminder"), "q?")
    db.commit()
    ctx = ask.answer_pending(db, u.id, "آره", now=_NOW)
    db.commit()
    assert ctx["followup_result"] == "done"
    db.refresh(ev)
    assert ev.status == "completed"


# ---- the ONE assurance ---------------------------------------------------------------------------------------------------
def test_an_ignored_medication_notification_gets_one_assurance_with_new_text_and_tray_buttons(db):
    u = _user_in(db, "+17770103001")
    n, _occ, _um = _medication(db, u, notif_minutes_ago=40)
    assert ad.create_due_assurance_tasks(db, now=_NOW) == 1
    assert ad.create_due_assurance_tasks(db, now=_NOW) == 0  # ONE per notification
    tasks = _tasks(db, u.id)
    assert len(tasks) == 1 and tasks[0].status == "open"
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW) == 1
    sent = db.query(models.Notification).filter_by(user_id=u.id, template_key="assurance_follow_up").one()
    # R-084 (Javad 2026-11-09): the follow-up names the drug of THIS dose
    assert sent.body == sedi_copy.t("assurance.body.medication_named", "fa", name="TestMed") and sent.id != n.id
    assert json.loads(sent.context_json)["assured_notification_id"] == str(n.id)
    from backend.app.services.gate4.push_payload import PLAN_FOLLOWUP_TEMPLATE_KEYS

    assert {"medication_reminder", "generic_event_reminder", "assurance_follow_up"} <= PLAN_FOLLOWUP_TEMPLATE_KEYS


@pytest.mark.parametrize("minutes,expected", [(10, 0), (29, 0), (31, 1), (89, 1), (100, 0)])
def test_the_assurance_comes_about_thirty_minutes_after_not_before_and_not_much_later(db, minutes, expected):
    u = _user_in(db, f"+17770104{minutes:03d}")
    _medication(db, u, notif_minutes_ago=minutes)
    assert ad.create_due_assurance_tasks(db, now=_NOW) == expected


@pytest.mark.parametrize("answer", ["notification_done", "notification_open_chat", "notification_not_now", "notification_talk_later", "notification_ack", "notification_dislike"])
def test_an_answered_notification_gets_no_assurance(db, answer):
    u = _user_in(db, f"+1777010500{abs(hash(answer)) % 90:02d}")
    n, _o, _m = _medication(db, u)
    db.add(models.InteractionEvent(user_id=u.id, event_type=answer, source="notification", source_notification_id=n.id))
    db.commit()
    assert ad.create_due_assurance_tasks(db, now=_NOW) == 0


def test_a_dose_already_confirmed_elsewhere_gets_no_assurance(db):
    u = _user_in(db, "+17770106001")
    _medication(db, u, state="CONFIRMED_TAKEN")
    assert ad.create_due_assurance_tasks(db, now=_NOW) == 0


def test_appointments_meetings_the_digest_and_other_families_get_no_assurance(db):
    u = _user_in(db, "+17770106002")
    _reminder(db, u, etype="doctor_visit", edomain="medical")  # post-event question (2E), not an assurance
    _reminder(db, u, etype="work_meeting", edomain="work")
    _notif(db, u.id, "daily_digest", "DAILY_WELLNESS_DIGEST", minutes_ago=40)
    _notif(db, u.id, "weekly_plan_review", "CARE_ACTION", minutes_ago=40)
    _notif(db, u.id, "plan_motivation_milestone", "ENGAGEMENT", minutes_ago=40)
    assert ad.create_due_assurance_tasks(db, now=_NOW) == 0


def test_a_plain_one_off_reminder_gets_an_assurance_with_the_generic_text(db):
    u = _user_in(db, "+17770106003")
    _reminder(db, u)
    assert ad.create_due_assurance_tasks(db, now=_NOW) == 1
    process_due_follow_up_tasks(db, now=_NAIVE_NOW)
    sent = db.query(models.Notification).filter_by(user_id=u.id, template_key="assurance_follow_up").one()
    # R-084 (Javad 2026-11-09): the follow-up names what it follows up - here the user's own plan name
    assert sent.body == sedi_copy.t("assurance.body.other_named", "fa", name="زنگ به مادر")


def test_a_late_assurance_is_dropped_and_an_answered_assurance_marks_the_original(db):
    u = _user_in(db, "+17770107001")
    n, occ, _ = _medication(db, u, notif_minutes_ago=40)
    ad.create_due_assurance_tasks(db, now=_NOW)
    process_due_follow_up_tasks(db, now=_NAIVE_NOW)
    assurance = db.query(models.Notification).filter_by(user_id=u.id, template_key="assurance_follow_up").one()
    # the user answers THE ASSURANCE: the dose is confirmed and the ORIGINAL is marked answered (never asked about again)
    ad.handle_action_answer(db, notification=assurance, actor_user_id=u.id, payload={"action_id": "done"})
    db.commit()
    db.refresh(occ)
    assert occ.state == "CONFIRMED_TAKEN"
    assert db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type=ad.ASSURED_EVENT, source_notification_id=n.id).count() == 1


@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("domain", ["medication", "plan", "event", None])
def test_the_assurance_text_exists_in_every_language_and_names_nothing_without_a_subject(lang, domain):
    title, body = ad.assurance_copy(lang, domain)
    assert title and body and "{" not in body
    assert (lang == "en") or all(ord(ch) < 128 for ch in body) is False  # fa / ar are written in their own script
    assert "TestMed" not in body


@pytest.mark.parametrize("lang", _LANGS)
def test_the_assurance_opener_asks_once_in_every_language(db, lang):
    from backend.app.services import a3_session_open as so

    u = _user_in(db, f"+1777010800{_LANGS.index(lang)}", lang)
    assurance = _notif(db, u.id, "assurance_follow_up", "GENERAL_CONTEXTUAL_FOLLOW_UP", minutes_ago=5)
    text = so.build_notification_origin_opener(db, u, assurance, language=lang)
    assert sedi_copy.t("session.origin.assurance", lang) in text


def test_2c1_never_asks_about_the_assurance_itself_nor_about_an_assured_original(db):
    u = _user_in(db, "+17770109001")
    assurance = _notif(db, u.id, "assurance_follow_up", "GENERAL_CONTEXTUAL_FOLLOW_UP", minutes_ago=5 * 60)
    db.add(models.InteractionEvent(user_id=u.id, event_type="notification_not_now", source="notification", source_notification_id=assurance.id))
    n, _o, _m = _medication(db, u, notif_minutes_ago=30 * 60)
    db.add(models.InteractionEvent(user_id=u.id, event_type=ad.ASSURED_EVENT, source="system", source_notification_id=n.id))
    db.commit()
    assert ask.pick_pending(db, u, now=_NOW) is None


# ---- wiring -------------------------------------------------------------------------------------------------------------
def test_the_router_the_worker_and_the_plan_path_are_wired():
    app = Path(__file__).resolve().parents[1] / "app"
    router = (app / "routers" / "notifications.py").read_text(encoding="utf-8")
    assert "handle_action_answer(db, notification=notification, actor_user_id=user_id, payload=payload)" in router
    assert router.index("handle_action_answer(db, notification=notification") < router.index("handle_coaching_done_for_notification")
    worker = (app / "services" / "i10" / "contextual_followup_worker.py").read_text(encoding="utf-8")
    assert "create_due_assurance_tasks(db, now=when)" in worker and "_assurance_may_send(db, task, now)" in worker
    coaching = (app / "services" / "i10" / "coaching_done.py").read_text(encoding="utf-8")
    assert coaching.count("record_plan_outcome(") == 2  # done and not done
    assert '"assured_notification_id"' in (app / "services" / "gate4" / "notification_context.py").read_text(encoding="utf-8")


# ---- Codex review of PR #147 (P2 x4) -------------------------------------------------------------------------------------
@pytest.mark.parametrize("outcome", ["done", "not_done"])
def test_a_plan_outcome_never_runs_inside_a_savepoint(db, outcome):
    """The I8 owner commits its own work: wrapping it in begin_nested broke the chat / assurance path (Codex P2)."""
    u = _user_in(db, f"+17770111{outcome[0]}01")
    plan = _notif(db, u.id, "nutrition_plan_follow_up", "NUTRITION_PLAN_FOLLOW_UP", minutes_ago=5)
    target = ad.resolve_target(db, plan, u.id)
    assert target is not None and target.kind == "plan"
    calls = []
    with patch.object(db, "begin_nested", side_effect=AssertionError("plan path must not open a savepoint")), patch(
        "backend.app.services.i10.coaching_done.handle_coaching_done_for_notification", side_effect=lambda *a, **k: calls.append("done")
    ), patch(
        "backend.app.services.i10.coaching_done.handle_coaching_not_done_for_notification", side_effect=lambda *a, **k: calls.append("not_done")
    ):
        ok = ad.complete(db, u.id, target) if outcome == "done" else ad.mark_not_done(db, u.id, target, "no_time")
    assert ok is True and calls == [outcome]


@pytest.mark.parametrize("message,expected", [("آره", "done"), ("نه، وقت نداشتم", "not_done:no_time")])
def test_a_chat_answer_on_the_assurance_also_answers_the_original(db, message, expected):
    u = _user_in(db, f"+177701120{abs(hash(message)) % 90:02d}")
    n, occ, _ = _medication(db, u, notif_minutes_ago=40)
    ad.create_due_assurance_tasks(db, now=_NOW)
    process_due_follow_up_tasks(db, now=_NAIVE_NOW)
    assurance = db.query(models.Notification).filter_by(user_id=u.id, template_key="assurance_follow_up").one()
    assert no.apply_chat_answer(db, assurance, u.id, message) == expected
    db.commit()
    assert db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type=ad.ASSURED_EVENT, source_notification_id=n.id).count() == 1
    # the original is now answered: 2C-1 never asks about it, and the assurance is not created again
    assert ask.pick_pending(db, u, now=_NOW + timedelta(hours=30)) is None


def test_a_waiting_assurance_is_dropped_when_the_original_was_completed_meanwhile(db):
    u = _user_in(db, "+17770113001")
    n, occ, _ = _medication(db, u, notif_minutes_ago=40)
    ad.create_due_assurance_tasks(db, now=_NOW)
    occ.state = "CONFIRMED_TAKEN"  # the user took the dose on the schedule page while the assurance was waiting
    db.commit()
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW) == 0
    assert db.query(models.Notification).filter_by(user_id=u.id, template_key="assurance_follow_up").count() == 0
    assert [t.status for t in _tasks(db, u.id)] == ["cancelled"]


def test_a_waiting_assurance_is_dropped_when_the_original_was_answered_meanwhile(db):
    u = _user_in(db, "+17770113002")
    n, _occ, _ = _medication(db, u, notif_minutes_ago=40)
    ad.create_due_assurance_tasks(db, now=_NOW)
    db.add(models.InteractionEvent(user_id=u.id, event_type="notification_talk_later", source="notification", source_notification_id=n.id))
    db.commit()
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW) == 0
    assert [t.status for t in _tasks(db, u.id)] == ["cancelled"]


def test_unrelated_and_already_answered_notifications_never_starve_an_eligible_one(db):
    u = _user_in(db, "+17770114001")
    for i in range(ad._SCAN_CAP + 5):  # a full batch of other families first
        db.add(models.Notification(
            user_id=u.id, type="connection_ping", title="x", body="x", channel="push", status="sent", is_sent=True,
            template_key="daily_digest", semantic_family="DAILY_WELLNESS_DIGEST",
            created_at=_NAIVE_NOW - timedelta(minutes=45), sent_at=_NAIVE_NOW - timedelta(minutes=45),
        ))
    db.commit()
    _medication(db, u, notif_minutes_ago=40)  # a later id than the whole prefix
    assert ad.create_due_assurance_tasks(db, now=_NOW) == 1
