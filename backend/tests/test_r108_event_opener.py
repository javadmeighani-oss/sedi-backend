"""R-108 / R-052 (2c-2, Javad 2026-11-21): the chat that opens from a care-appointment push continues THAT appointment, not a generic greeting.

The push («امروز ساعت ۱۵ «فیزیوتراپی زانو» داری») and the opener are built from the same event; when the shared care state holds an open
issue, the opener asks ONE specific question about it. Real session (in-memory SQLite): sweep -> worker -> notification -> opener.
"""
import pytest

from backend.app import models, sedi_copy
from backend.app.services.i10 import event_care as ec
from backend.app.services.notification_openers import _key_for, family_opener
from backend.tests.test_r108_event_care import DAY, _add_event, _pinned, _tasks, _utc, db, user  # noqa: F401  (real-session fixtures/helpers)


def _now(monkeypatch, local):
    """Pin «now» for the freshness checks (the push was sent at 09:00 on DAY; the user opens it later)."""
    import datetime as dt

    real = dt.datetime
    moment = _utc(f"{DAY} {local}")

    class Pinned(real):
        @classmethod
        def now(cls, tz=None):
            return moment.replace(tzinfo=dt.timezone.utc) if tz else moment

    monkeypatch.setattr(ec, "datetime", Pinned)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    """The opener checks the appointment is still upcoming against the real clock: pin it to 10:00 on the appointment's day (R-104)."""
    _now(monkeypatch, "10:00")


@pytest.fixture(autouse=True)
def _followups_on(monkeypatch):
    monkeypatch.setenv("SEDI_I10_CONTEXTUAL_FOLLOWUP_ENABLED", "1")


def _send(db, user, kind, **event):
    """Create the appointment, run the sweep + the real worker at the due time, return the notification the user got."""
    from backend.app.services.i10 import contextual_followup_worker as worker

    _add_event(db, user, **event)
    due = {ec.KIND_DAY_OF: ("08:55", "09:00"), ec.KIND_PRE: ("12:55", "13:00")}[kind]
    ec.create_due_event_care_tasks(db, now=_utc(f"{DAY} {due[0]}"))
    task = [t for k, t in _tasks(db) if k == kind][0]
    assert worker.process_single_follow_up_task(db, task, now=_utc(f"{DAY} {due[1]}")) is True
    return db.query(models.Notification).filter(models.Notification.source_id == str(task.id)).first()


def _issue(db, user, text):
    from backend.app.services.candidate_promotion_service import _merge_list_value
    from backend.app.services.i6.memory_writes import write_fact

    write_fact(db, user.id, "medical", "health_concerns", _merge_list_value(db, user.id, "medical", "health_concerns", text),
               source="chat", provenance_class="USER_STATED", commit=True)


# --- the subject ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("template", [ec.KIND_DAY_OF, ec.KIND_PRE])
def test_the_two_messages_belong_to_the_event_care_subject(template):
    assert _key_for(models.Notification(user_id=1, template_key=template)) == "event_care"


def test_other_templates_are_not_mistaken_for_it():
    assert _key_for(models.Notification(user_id=1, template_key="event_reminder")) != "event_care"
    assert _key_for(models.Notification(user_id=1, template_key="post_event_follow_up")) == "post_event"


# --- the opener, from the real push ---------------------------------------------------------------------------------------------------------------
def test_the_day_of_opener_names_the_same_appointment_as_the_push(db, user):
    n = _send(db, user, ec.KIND_DAY_OF, title="فیزیوتراپی زانو", location="کلینیک مهر")
    opener = family_opener(db, user, n, language="fa", name="سارا")
    assert opener == "سارا، امروز ساعت 15:00 «فیزیوتراپی زانو» در کلینیک مهر داری. برای رفتن آماده‌ای؟"
    assert "فیزیوتراپی زانو" in n.body and "15:00" in n.body and "کلینیک مهر" in n.body  # the push and the opener say the same thing


def test_the_pre_check_opener_asks_how_the_user_is_now(db, user):
    n = _send(db, user, ec.KIND_PRE, title="فیزیوتراپی زانو")
    assert family_opener(db, user, n, language="fa") == "ساعت 15:00 «فیزیوتراپی زانو» داری. الان حالت چطور است؟"


def test_an_open_issue_makes_the_question_specific(db, user):
    _issue(db, user, "درد زانو")
    day = family_opener(db, user, _send(db, user, ec.KIND_DAY_OF, title="فیزیوتراپی زانو"), language="fa")
    assert day == "امروز ساعت 15:00 «فیزیوتراپی زانو» داری. دربارهٔ «درد زانو» چیزی هست که بخواهی در این نوبت بگویی یا بپرسی؟"
    pre_note = _send(db, user, ec.KIND_PRE, title="فیزیوتراپی زانو")
    assert family_opener(db, user, pre_note, language="fa") == "ساعت 15:00 «فیزیوتراپی زانو» داری. «درد زانو» الان چطور است؟"


def test_it_is_one_question_only(db, user):
    _issue(db, user, "درد زانو")
    text = family_opener(db, user, _send(db, user, ec.KIND_DAY_OF, title="فیزیوتراپی زانو"), language="fa")
    assert text.count("؟") == 1


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_every_language_renders_every_variant(lang):
    for which in ("event_day_of", "event_pre"):
        for suffix in ("", "_issue"):
            text = sedi_copy.t(f"session.origin.{which}{suffix}", lang, time="15:00", title="X", place=sedi_copy.t("event_care.place", lang, location="Y"), issue="Z")
            assert "{" not in text and "X" in text and "15:00" in text and "Y" in text and ("Z" in text) == bool(suffix)


def test_english_and_arabic_users_get_their_own_language(db, user):
    user.preferred_language = "en"
    db.commit()
    n = _send(db, user, ec.KIND_PRE, title="Physiotherapy", location="Mehr Clinic")
    assert family_opener(db, user, n, language="en", name="Sara") == "Sara, At 15:00 you have “Physiotherapy” at Mehr Clinic. How are you feeling right now?"


# --- when the appointment or the consent is gone ----------------------------------------------------------------------------------------------------
def test_a_vanished_appointment_leaves_the_generic_opener(db, user):
    n = _send(db, user, ec.KIND_DAY_OF)
    db.query(models.UserEvent).delete()
    db.commit()
    assert family_opener(db, user, n, language="fa") is None  # the caller keeps its generic fallback


def test_without_memory_read_consent_the_issue_is_not_mentioned(db, user):
    from backend.app.services.i6 import consent_service as consent

    _issue(db, user, "درد زانو")
    n = _send(db, user, ec.KIND_DAY_OF, title="فیزیوتراپی زانو")
    consent.revoke_memory_consent(db, user.id)
    assert "درد زانو" not in (family_opener(db, user, n, language="fa") or "")


def test_the_session_open_route_uses_the_specific_opener(db, user):
    """The app's session-open path (a3) reaches the same text through family_opener - not the generic acknowledgment."""
    from backend.app.services import a3_session_open

    n = _send(db, user, ec.KIND_DAY_OF, title="فیزیوتراپی زانو")
    text = a3_session_open.build_notification_origin_opener(db, user, n, language="fa", preferred_name="سارا")
    assert text == "سارا، امروز ساعت 15:00 «فیزیوتراپی زانو» داری. برای رفتن آماده‌ای؟"


# --- Codex round 1 on PR 209 ------------------------------------------------------------------------------------------------------------------
def test_p2_an_old_push_of_a_cancelled_or_past_appointment_leaves_the_generic_opener(db, user, monkeypatch):
    n = _send(db, user, ec.KIND_DAY_OF, title="فیزیوتراپی زانو")
    _now(monkeypatch, "10:00")
    assert family_opener(db, user, n, language="fa") is not None                     # still upcoming at 10:00: specific
    _now(monkeypatch, "15:30")
    assert family_opener(db, user, n, language="fa") is None                         # the appointment has started: not «today you have»
    _now(monkeypatch, "10:00")
    event = db.query(models.UserEvent).first()
    event.status = "cancelled"
    db.commit()
    assert family_opener(db, user, n, language="fa") is None                         # cancelled


def test_p2_an_appointment_moved_to_another_day_is_not_announced_as_today(db, user, monkeypatch):
    from datetime import timedelta

    n = _send(db, user, ec.KIND_DAY_OF, title="فیزیوتراپی زانو")
    event = db.query(models.UserEvent).first()
    event.starts_at = event.starts_at + timedelta(days=3)
    db.commit()
    _now(monkeypatch, "10:00")
    assert family_opener(db, user, n, language="fa") is None
    # the pre-check wording has no «today» claim: a still-future appointment keeps its specific opener
    pre_event = db.query(models.UserEvent).first()
    pre_event.starts_at = pre_event.starts_at - timedelta(days=3)
    db.commit()
    assert family_opener(db, user, n, language="fa") is not None


# --- 2c-3: the whole appointment loop, push -> opener -> the user's answer -> memory -> the picture (real session, no owner stubbed) -----------------
def _delivered(db, n, at=None):
    """What the delivery pipeline does after a successful send (the worker only queues the notification)."""
    from datetime import datetime

    n.is_sent, n.status, n.sent_at = True, "sent", at or datetime.utcnow()
    db.commit()


def _loop(db, user, kind=ec.KIND_PRE):
    _issue(db, user, "درد زانو")
    n = _send(db, user, kind, title="فیزیوتراپی زانو")
    _delivered(db, n)
    return n


def test_loop_the_answer_to_the_pre_check_is_remembered_and_the_picture_follows(db, user):
    from backend.app.services import care_state as cs
    from backend.app.services.care_journey import journey as j
    from backend.app.services.status_report import builder as report

    n = _loop(db, user)
    assert family_opener(db, user, n, language="fa") == "ساعت 15:00 «فیزیوتراپی زانو» داری. «درد زانو» الان چطور است؟"
    state = cs.get_care_state(db, user.id)
    assert state.issues[0].status == "open" and not state.has_open_journey and state.events          # the appointment is part of the picture
    assert j.apply_status(db, user.id, "الان بهترم", "fa") == "better"                              # the answer to the push's question
    state = cs.get_care_state(db, user.id)
    assert state.issues[0].status == "better" and not state.has_open_journey                         # remembered; no chain was needed
    assert "رو به بهبود" in cs.summary_line(state, "fa")
    sections = {s["key"]: [x["text"] for x in s["lines"]] for s in report.build_status_report(db, user.id, "doctor_visit", "fa")["sections"]}
    assert sections                                                                                   # the report reads the same picture


def test_loop_worse_after_the_push_starts_the_hours_level_chain(db, user):
    from backend.app.services import care_state as cs
    from backend.app.services.care_journey import journey as j

    n = _loop(db, user, ec.KIND_DAY_OF)
    assert family_opener(db, user, n, language="fa") is not None
    assert j.apply_status(db, user.id, "حالم بدتر شده", "fa") == "worse"
    state = cs.get_care_state(db, user.id)
    assert state.issues[0].status == "worse" and state.has_open_journey and state.is_acute          # Sedi keeps following, within hours


def test_loop_a_plain_better_without_a_push_or_an_issue_changes_nothing(db, user):
    from backend.app.services import care_state as cs
    from backend.app.services.care_journey import journey as j

    assert j.apply_status(db, user.id, "الان بهترم", "fa") is None                                   # no push, no issue
    _issue(db, user, "درد زانو")
    assert j.apply_status(db, user.id, "الان بهترم", "fa") is None                                   # an issue but no appointment push
    assert cs.get_care_state(db, user.id).issues[0].status == "open"


def test_loop_an_old_push_or_revoked_consent_changes_nothing(db, user):
    from datetime import timedelta

    from backend.app.services.care_journey import journey as j
    from backend.app.services.i6 import consent_service as consent

    n = _loop(db, user)
    n.sent_at = n.sent_at - timedelta(hours=30)
    db.commit()
    assert j.apply_status(db, user.id, "الان بهترم", "fa") is None                                   # the push was sent more than 24 h ago
    n.sent_at = n.sent_at + timedelta(hours=30)
    db.commit()
    consent.revoke_memory_consent(db, user.id)
    assert j.apply_status(db, user.id, "الان بهترم", "fa") is None                                   # nothing is read or written without consent


def test_p2_a_push_that_was_never_delivered_does_not_count(db, user):
    """Codex round 1 on PR 210: queued / failed / blocked appointment notifications were never seen by the user."""
    from backend.app.services import care_state as cs
    from backend.app.services.care_journey import journey as j

    _issue(db, user, "درد زانو")
    n = _send(db, user, ec.KIND_PRE, title="فیزیوتراپی زانو")                                       # created by the worker, not yet sent
    assert j.apply_status(db, user.id, "الان بهترم", "fa") is None and j.apply_status(db, user.id, "حالم بدتر شده", "fa") is None
    n.status = "failed"
    db.commit()
    assert j.apply_status(db, user.id, "الان بهترم", "fa") is None
    state = cs.get_care_state(db, user.id)
    assert state.issues[0].status == "open" and not state.has_open_journey
    _delivered(db, n)
    assert j.apply_status(db, user.id, "الان بهترم", "fa") == "better"
