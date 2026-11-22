"""R-108 / R-052 (2c-2, Javad 2026-11-21): the chat that opens from a care-appointment push continues THAT appointment, not a generic greeting.

The push («امروز ساعت ۱۵ «فیزیوتراپی زانو» داری») and the opener are built from the same event; when the shared care state holds an open
issue, the opener asks ONE specific question about it. Real session (in-memory SQLite): sweep -> worker -> notification -> opener.
"""
import pytest

from backend.app import models, sedi_copy
from backend.app.services.i10 import event_care as ec
from backend.app.services.notification_openers import _key_for, family_opener
from backend.tests.test_r108_event_care import DAY, _add_event, _pinned, _tasks, _utc, db, user  # noqa: F401  (real-session fixtures/helpers)


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
