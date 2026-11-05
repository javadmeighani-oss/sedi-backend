"""R-071 / R-072 (step 2E): the outcome of an event is asked (kind-specific), understood and remembered.

Matrix: event types x kinds, windows (time zone aware), languages, replies (attended / missed + reason), channels (tray opener /
2C-1 first chat message), ownership, idempotency, wiring.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import models, sedi_copy
from backend.app.services import a3_session_open as so
from backend.app.services import notification_followup_ask as ask
from backend.app.services import notification_openers as no
from backend.app.services.i10 import event_outcome as eo
from backend.app.services.i10.contextual_followup_worker import process_due_follow_up_tasks
from backend.app.services.i7 import user_done
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

_LANGS = ["fa", "ar", "en"]
_NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)  # 12:30 in Tehran
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


def _local(hour, minute=0):
    """Naive local (Tehran) wall-clock time on the day of _NOW - the way UserEvent.starts_at is stored."""
    return datetime(2026, 11, 5, hour, minute)


def _event(db, u, *, etype="doctor_visit", domain="medical", starts=None, ends=None, status="scheduled", rule=None, title="دکتر قلب"):
    ev = models.UserEvent(
        user_id=u.id, title=title, event_domain=domain, event_type=etype, starts_at=starts or _local(10, 30), ends_at=ends,
        timezone="Asia/Tehran", status=status, recurrence_rule=rule,
    )
    db.add(ev)
    db.commit()
    return ev


def _tasks(db, uid):
    return db.query(models.CareFollowUpTask).filter(models.CareFollowUpTask.user_id == uid).all()


def _sent(db, uid):
    return db.query(models.Notification).filter_by(user_id=uid, template_key="post_event_follow_up").order_by(models.Notification.id.desc()).first()


# ---- which events, which question ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("etype,domain,expected", [
    ("doctor_visit", "medical", "visit"), ("imaging", "medical", "visit"), ("surgery", "medical", "visit"), ("care_followup", "care", "visit"),
    ("medical_follow_up", "medical", "visit"), ("physiotherapy", "medical", "visit"), ("other", "medical", "visit"),
    ("lab_test", "medical", "lab"), ("work_meeting", "work", "meeting"), ("other", "work", "meeting"), ("other", "education", "meeting"),
    ("exam", "education", "exam"), ("deadline", "work", "deadline"),
    # everyday events keep the 2D assurance; notes / birthdays are not outcomes
    ("other", "personal", None), ("other", "other", None), ("other", "lifestyle", None), ("birthday", "personal", None),
    ("important_day", "personal", None), ("memory_note", "other", None),
])
def test_the_kind_of_question_follows_the_kind_of_event(db, etype, domain, expected):
    u = _user_in(db, f"+177702{abs(hash((etype, domain))) % 90000 + 10000}")
    assert eo.outcome_kind(_event(db, u, etype=etype, domain=domain)) == expected


def test_a_repeating_event_has_no_outcome_question(db):
    u = _user_in(db, "+17770200001")
    assert eo.outcome_kind(_event(db, u, rule="FREQ=WEEKLY")) is None


# ---- the sweep ----------------------------------------------------------------------------------------------------------
def test_the_sweep_is_time_zone_aware_and_creates_exactly_one_task(db):
    u = _user_in(db, "+17770201001")
    # 10:30 Tehran = 07:00 UTC, one hour long -> ended 08:00 UTC; at 09:00 UTC the 30-minute mark has passed
    done = _event(db, u, starts=_local(10, 30))
    # 11:30 Tehran = 08:00 UTC -> ends 09:00 UTC: not over yet (a naive-UTC reading would wrongly think it is)
    running = _event(db, u, starts=_local(11, 30), title="هنوز نرسیده")
    assert eo.create_due_event_outcome_tasks(db, now=_NOW) == 1
    assert eo.create_due_event_outcome_tasks(db, now=_NOW) == 0  # ONE per event
    tasks = _tasks(db, u.id)
    assert len(tasks) == 1 and tasks[0].source == "post_event"
    from backend.app.services.i10.contextual_followup_task_meta import parse_bounded_meta

    meta = parse_bounded_meta(tasks[0].description)[1]
    assert meta.user_event_id == done.id and meta.domain == "visit" and running.id != meta.user_event_id


@pytest.mark.parametrize("ago_min,expected", [(10, 0), (29, 0), (31, 1), (23 * 60, 1), (25 * 60, 0)])
def test_the_question_comes_thirty_minutes_after_the_end_and_not_after_a_day(db, ago_min, expected):
    u = _user_in(db, f"+177702020{ago_min:05d}"[:13])
    end_utc = _NAIVE_NOW - timedelta(minutes=ago_min)
    start_local = end_utc - timedelta(hours=1) + timedelta(hours=3, minutes=30)  # UTC -> Tehran wall clock
    _event(db, u, starts=start_local)
    assert eo.create_due_event_outcome_tasks(db, now=_NOW) == expected


def test_an_end_time_of_its_own_is_honoured(db):
    u = _user_in(db, "+17770203001")
    _event(db, u, starts=_local(10, 30), ends=_local(13, 0))  # a 2.5 h event ends 09:30 UTC: still running at 09:00 UTC
    assert eo.create_due_event_outcome_tasks(db, now=_NOW) == 0


@pytest.mark.parametrize("status", ["cancelled", "missed"])
def test_cancelled_events_are_never_asked(db, status):
    u = _user_in(db, f"+1777020400{len(status)}")
    _event(db, u, status=status)
    assert eo.create_due_event_outcome_tasks(db, now=_NOW) == 0


def test_a_completed_event_is_still_asked_what_came_of_it(db):
    u = _user_in(db, "+17770205001")
    _event(db, u, status="completed")  # marked attended on the schedule page: the OUTCOME (what the doctor said) is still worth asking
    assert eo.create_due_event_outcome_tasks(db, now=_NOW) == 1


# ---- the notification ---------------------------------------------------------------------------------------------------
def test_the_worker_sends_one_generic_push_that_points_at_its_task(db):
    u = _user_in(db, "+17770206001")
    ev = _event(db, u)
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW) == 1
    n = _sent(db, u.id)
    task = _tasks(db, u.id)[0]
    assert n is not None and n.source_id == str(task.id) and task.status == "notified"
    assert ev.title not in (n.body or "") and ev.title not in (n.title or "")  # lock-screen safe: the title never leaves the app
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW) == 0


def test_a_work_meeting_is_not_a_health_alert(db):
    u = _user_in(db, "+17770206002")
    _event(db, u, etype="work_meeting", domain="work", title="جلسه")
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW) == 1
    assert _sent(db, u.id).type == "connection_ping"
    m = _user_in(db, "+17770206003")
    _event(db, m)
    process_due_follow_up_tasks(db, now=_NAIVE_NOW)
    assert _sent(db, m.id).type == "health_alert"


def test_a_late_or_cancelled_post_event_task_is_dropped(db):
    u = _user_in(db, "+17770207001")
    ev = _event(db, u)
    eo.create_due_event_outcome_tasks(db, now=_NOW)
    ev.status = "cancelled"
    db.commit()
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW) == 0
    assert [t.status for t in _tasks(db, u.id)] == ["cancelled"]
    v = _user_in(db, "+17770207002")
    _event(db, v)
    eo.create_due_event_outcome_tasks(db, now=_NOW)
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW + timedelta(hours=30)) == 0  # more than a day after the end


# ---- the in-app question ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", _LANGS)
@pytest.mark.parametrize("etype,domain,kind", [("doctor_visit", "medical", "visit"), ("lab_test", "medical", "lab"), ("work_meeting", "work", "meeting"),
                                               ("exam", "education", "exam"), ("deadline", "work", "deadline")])
def test_the_opener_asks_the_question_of_this_kind_and_names_the_users_event(db, lang, etype, domain, kind):
    u = _user_in(db, f"+177702080{abs(hash((lang, kind))) % 9000 + 1000}", lang)
    ev = _event(db, u, etype=etype, domain=domain, title="عنوان من", starts=_local(7, 0))
    process_due_follow_up_tasks(db, now=_NAIVE_NOW)
    n = _sent(db, u.id)
    text = so.build_notification_origin_opener(db, u, n, language=lang)
    assert "عنوان من" in text and sedi_copy.t(f"session.origin.post_event.{kind}", lang, title="عنوان من") in text
    assert "{" not in text and text.count("؟") + text.count("?") == 1


def test_the_opener_never_names_another_users_event_and_falls_back_to_the_generic_line(db):
    u = _user_in(db, "+17770209001")
    other = _user_in(db, "+17770209002")
    _event(db, other, title="راز دیگری")
    process_due_follow_up_tasks(db, now=_NAIVE_NOW)
    theirs = _sent(db, other.id)
    stolen = so.build_notification_origin_opener(db, u, theirs, language="fa")
    assert "راز دیگری" not in stolen and sedi_copy.t("session.origin.post_event", "fa") in stolen


# ---- reading the reply --------------------------------------------------------------------------------------------------
_REPLIES = [
    ("رفتم، دکتر گفت قندم کمی بالاست", ("attended", None)), ("آزمایش انجام شد جواب پس‌فردا", ("attended", None)),
    ("جلسه خوب گذشت و یک کار جدید گرفتم", ("attended", None)), ("خوب بود", ("attended", None)),
    ("went fine, the doctor said to rest", ("attended", None)), ("it went well", ("attended", None)), ("I handed it in yesterday evening", ("attended", None)),
    ("ذهبت وقال لي الطبيب أن أرتاح", ("attended", None)), ("تمت الزيارة", ("attended", None)),
    ("نرفتم", ("missed", "other")), ("نشد، وقت نداشتم", ("missed", "no_time")), ("کنسل شد", ("missed", "other")), ("نتونستم چون حالم بد بود", ("missed", "not_feeling_well")),
    ("I could not go, too busy", ("missed", "no_time")), ("it was postponed", ("missed", "other")), ("لم أذهب", ("missed", "other")), ("تأجل الموعد", ("missed", "other")),
    # never guessed
    ("چرا می‌پرسی؟", None), ("سلام", None), ("باشه", None), ("", None), ("how are you?", None),
]


@pytest.mark.parametrize("message,expected", _REPLIES)
def test_the_reply_is_read_cautiously(message, expected):
    assert eo.parse_attendance(message) == expected


# ---- recording ----------------------------------------------------------------------------------------------------------
def _notified(db, u, **kw):
    ev = _event(db, u, **kw)
    process_due_follow_up_tasks(db, now=_NAIVE_NOW)
    return ev, _sent(db, u.id)


def test_an_attended_reply_completes_the_event_and_writes_i7(db):
    u = _user_in(db, "+17770210001")
    ev, n = _notified(db, u)
    assert no.apply_chat_answer(db, n, u.id, "رفتم، دکتر گفت قندم کمی بالاست") == "attended"
    db.commit()
    db.refresh(ev)
    assert ev.status == "completed"
    assert user_done.done_counts_for_day(db, u.id, ev.starts_at.date()) == {"appointment": 1}
    assert no.apply_chat_answer(db, n, u.id, "رفتم و دکتر دوباره گفت") is None  # replay never double-counts


def test_a_missed_reply_is_memory_with_its_reason_and_keeps_the_event_open(db):
    u = _user_in(db, "+17770210002")
    ev, n = _notified(db, u)
    assert no.apply_chat_answer(db, n, u.id, "نشد، وقت نداشتم") == "missed:no_time"
    db.commit()
    db.refresh(ev)
    assert ev.status == "scheduled"
    counts = user_done.not_done_counts_for_day(db, u.id, ev.starts_at.date())
    assert counts.get("appointment") == 1 and counts.get("reason.no_time") == 1


def test_nobody_elses_event_is_ever_recorded(db):
    u = _user_in(db, "+17770210003")
    other = _user_in(db, "+17770210004")
    ev, n = _notified(db, other)
    assert no.apply_chat_answer(db, n, u.id, "رفتم، دکتر گفت") is None
    db.refresh(ev)
    assert ev.status == "scheduled"


def test_an_unclear_reply_changes_nothing(db):
    u = _user_in(db, "+17770210005")
    ev, n = _notified(db, u)
    assert no.apply_chat_answer(db, n, u.id, "سلام") is None
    db.refresh(ev)
    assert ev.status == "scheduled"


# ---- a day of silence: the first chat message asks again (R-072) ----------------------------------------------------------
def test_silence_for_a_day_is_followed_up_in_the_first_chat_message_with_the_outcome_question(db):
    u = _user_in(db, "+17770211001")
    ev, n = _notified(db, u)
    n.created_at = n.sent_at = _NAIVE_NOW  # the push went out at _NOW
    n.status = "sent"
    db.commit()
    later = _NOW + timedelta(hours=26)
    pending = ask.pick_pending(db, u, now=later)
    assert pending is not None and pending.kind == "unanswered" and pending.subject_key == "post_event"
    assert ask.question_text(pending, "fa") == sedi_copy.t("ask.outcome", "fa")
    ask.mark_asked(db, u.id, pending, ask.question_text(pending, "fa"))
    db.query(models.InteractionEvent).filter_by(user_id=u.id, event_type=ask.ASKED_EVENT).update({"created_at": later.replace(tzinfo=None)})
    db.commit()
    ctx = ask.answer_pending(db, u.id, "رفتم، دکتر گفت باید آزمایش بدهم", now=later)
    db.commit()
    assert ctx["followup_result"] == "attended"
    db.refresh(ev)
    assert ev.status == "completed"


def test_an_outcome_recorded_elsewhere_is_never_asked_again(db):
    u = _user_in(db, "+17770211002")
    ev, n = _notified(db, u)
    n.created_at = n.sent_at = _NAIVE_NOW
    n.status = "sent"
    db.commit()
    user_done.record(db, u.id, kind="event", ref_id=ev.id, day=ev.starts_at.date(), hhmm=None, domain="appointment", done=True)
    db.commit()
    assert ask.pick_pending(db, u, now=_NOW + timedelta(hours=26)) is None


# ---- wiring -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", _LANGS)
def test_the_unanswered_outcome_question_has_one_question_mark(lang):
    text = ask.question_text(ask.Pending(1, "unanswered", "post_event"), lang)
    assert text.count("؟") + text.count("?") == 1 and "{" not in text


def test_the_worker_the_adapter_and_the_model_notes_are_wired():
    app = Path(__file__).resolve().parents[1] / "app"
    worker = (app / "services" / "i10" / "contextual_followup_worker.py").read_text(encoding="utf-8")
    assert "create_due_event_outcome_tasks(db, now=when)" in worker and "post_event_may_send(db, task, now)" in worker
    from backend.app.core.conversation.brain import _format_notification_context_block

    attended = _format_notification_context_block({"template_key": "post_event_follow_up", "opening_message": "q?", "followup_result": "attended"})
    assert "ONE concrete step" in attended and "ask once for the date" in attended
    missed = _format_notification_context_block({"template_key": "post_event_follow_up", "opening_message": "q?", "followup_result": "missed:no_time"})
    assert "did not take place" in missed and "no guilt" in missed


# ---- Codex review of PR #148 --------------------------------------------------------------------------------------------
_NOT_ATTENDANCE = [
    # negations / unrelated text must never become a permanent «done» (Codex P1)
    "I have not done it", "I haven't done it yet", "I did not attend the appointment", "I didn't go", "I want to discuss something else",
    "I need to talk about my sleep", "can we talk about something different today", "the doctor was not available",
    "هنوز انجام ندادم", "می‌خواهم درباره‌ی چیز دیگری حرف بزنم", "امروز حالم خوب نیست", "دکتر نبود", "نه نرفتم",
    "لم أنجز ذلك بعد", "أريد أن أتحدث عن شيء آخر", "الطبيب لم يكن موجودا",
    # both named, or only a question
    "رفتم ولی نشد", "I went but it was cancelled", "رفتی؟",
]


@pytest.mark.parametrize("message", _NOT_ATTENDANCE)
def test_attendance_needs_affirmative_evidence(message):
    verdict = eo.parse_attendance(message)
    assert verdict is None or verdict[0] == "missed", verdict


@pytest.mark.parametrize("message", ["I have not done it", "I did not attend the appointment", "هنوز انجام ندادم", "لم أنجز ذلك"])
def test_an_explicit_not_attended_reply_is_missed_never_attended(message):
    verdict = eo.parse_attendance(message)
    assert verdict is not None and verdict[0] == "missed"


@pytest.mark.parametrize("message", ["I want to discuss something else", "امروز حالم خوب نیست", "the doctor was not available"])
def test_an_unrelated_or_negated_reply_records_nothing_in_the_owner_or_i7(db, message):
    u = _user_in(db, f"+177702{abs(hash(message)) % 90000 + 10000}")
    ev, n = _notified(db, u)
    assert no.apply_chat_answer(db, n, u.id, message) is None
    db.refresh(ev)
    assert ev.status == "scheduled"
    assert user_done.done_counts_for_day(db, u.id, ev.starts_at.date()) == {}


def test_an_event_moved_into_the_future_is_not_asked_about_before_it_ends(db):
    u = _user_in(db, "+17770212001")
    ev = _event(db, u)
    eo.create_due_event_outcome_tasks(db, now=_NOW)
    ev.starts_at = _local(20, 0)  # the user moved the appointment to this evening while the question waited
    db.commit()
    assert process_due_follow_up_tasks(db, now=_NAIVE_NOW) == 0
    assert _sent(db, u.id) is None and [t.status for t in _tasks(db, u.id)] == ["open"]
