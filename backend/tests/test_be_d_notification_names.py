"""BE-D (Javad 2026-11-09, R-084): the full name the user gave a plan is in EVERY reminder, and the follow-up push (and the chat opened
from it) names again what it follows up - a drug, a plan (fa / ar / en)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app import models, sedi_copy
from backend.app.services.i10 import action_done as ad
from backend.app.services.i10 import event_reminder_i10_adapter as er
from backend.app.services.i10.contextual_followup_i10_adapter import _assurance_copy
from backend.app.services.notification_openers import family_opener

LANGS = ("fa", "ar", "en")
LONG_NAME = "ویزیت دکتر رضایی برای بررسی نتیجه‌ی آزمایش خون و سونوگرافی کامل"


def _event(title, event_type="doctor_visit"):
    return SimpleNamespace(title=title, event_type=event_type)


# ---- reminders ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("event_type", ["doctor_visit", "lab_test", "imaging", "surgery", "other", "work_meeting"])
@pytest.mark.parametrize("medical", [True, False])
def test_every_reminder_carries_the_full_name_the_user_gave(lang, event_type, medical):
    _title, body, _template = er._reminder_copy(_event(LONG_NAME, event_type), medical=medical, lang=lang, offset_min=60)
    assert LONG_NAME in body, (lang, event_type, medical, body)  # the whole name, never cut


@pytest.mark.parametrize("lang", LANGS)
def test_generic_default_titles_are_not_repeated_as_if_the_user_wrote_them(lang):
    for default in er._DEFAULT_LABELS:
        _t, body, _k = er._reminder_copy(_event(default), medical=True, lang=lang, offset_min=0)
        assert f"«{default}»" not in body and f": {default}" not in body


@pytest.mark.parametrize("lang", LANGS)
def test_the_template_and_family_of_a_medical_reminder_stay_medical(lang):
    _t, _b, template = er._reminder_copy(_event(LONG_NAME, "doctor_visit"), medical=True, lang=lang, offset_min=0)
    assert template == "doctor_appointment_reminder"
    _t, _b, template = er._reminder_copy(_event(LONG_NAME, "lab_test"), medical=True, lang=lang, offset_min=0)
    assert template == "lab_appointment_reminder"
    _t, _b, template = er._reminder_copy(_event(LONG_NAME, "other"), medical=False, lang=lang, offset_min=0)
    assert template == "generic_event_reminder"


# ---- follow-up copy ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("domain", ["medication", "event", "other"])
def test_a_follow_up_with_a_known_subject_names_it(lang, domain):
    title, body = ad.assurance_copy(lang, domain, "Metformin")
    assert "Metformin" in body and "{" not in body and title


@pytest.mark.parametrize("lang", LANGS)
def test_a_follow_up_without_a_subject_keeps_the_generic_text(lang):
    assert ad.assurance_copy(lang, "medication", "")[1] == sedi_copy.t("assurance.body.medication", lang)
    assert ad.assurance_copy(lang, "other", None)[1] == sedi_copy.t("assurance.body.other", lang)
    assert ad.assurance_copy(lang, "plan", "x")[1] == sedi_copy.t("assurance.body.plan", lang)  # plan items keep their own wording


def test_the_new_copy_keys_exist_in_three_languages_with_the_same_placeholder():
    for key in ("assurance.body.medication_named", "assurance.body.other_named", "session.origin.assurance_named"):
        block = sedi_copy.by_lang(key)
        assert set(block) >= {"fa", "ar", "en"}
        assert all("{name}" in block[lang] for lang in LANGS)


# ---- subject lookup against the real tables -------------------------------------------------------------------------------------------------
def _user(db):
    u = models.User(name="names", secret_key="bed-test", preferred_language="fa")
    db.add(u)
    db.flush()
    return u


def _medication_notification(db, u, name="Metformin"):
    med = models.Medication(name=name)
    db.add(med)
    db.flush()
    um = models.UserMedication(user_id=u.id, medication_id=med.id)
    db.add(um)
    db.flush()
    occ = models.MedicationDoseOccurrence(
        user_id=u.id, user_medication_id=um.id, scheduled_for=datetime.now(timezone.utc), occurrence_key=f"bed:{um.id}:1"
    )
    db.add(occ)
    db.flush()
    n = models.Notification(
        user_id=u.id, type="HEALTH", body="x", template_key="medication_reminder", source_id=str(occ.id), status="sent"
    )
    db.add(n)
    db.flush()
    return n


def _event_notification(db, u, title):
    ev = models.UserEvent(user_id=u.id, title=title, starts_at=datetime(2026, 11, 10, 17, 0))
    db.add(ev)
    db.flush()
    n = models.Notification(user_id=u.id, type="INSIGHT", body="x", template_key="generic_event_reminder", source_id=str(ev.id), status="sent")
    db.add(n)
    db.flush()
    return n


def test_the_subject_of_a_dose_reminder_is_the_drug_name(db):
    u = _user(db)
    n = _medication_notification(db, u, "Metformin 500")
    assert ad.subject_name(db, n, u.id) == "Metformin 500"


def test_the_subject_of_an_event_reminder_is_the_users_own_title_in_full(db):
    u = _user(db)
    n = _event_notification(db, u, LONG_NAME)
    assert ad.subject_name(db, n, u.id) == LONG_NAME


def test_a_default_title_or_someone_elses_notification_has_no_subject(db):
    u = _user(db)
    other = models.User(name="other", secret_key="bed-test2", preferred_language="fa")
    db.add(other)
    db.flush()
    default = next(iter(er._DEFAULT_LABELS))
    assert ad.subject_name(db, _event_notification(db, u, default), u.id) == ""
    mine = _medication_notification(db, u, "Secret")
    assert ad.subject_name(db, mine, other.id) == ""  # ownership is checked
    assert ad.subject_name(db, None, u.id) == ""


def test_the_assurance_push_names_the_drug_and_the_chat_opener_names_it_again(db):
    from backend.app.services.i10.contextual_followup_task_meta import BoundedFollowUpMeta

    u = _user(db)
    original = _medication_notification(db, u, "Metformin 500")
    meta = BoundedFollowUpMeta(follow_up_kind="assurance", source_notification_id=int(original.id), domain="medication")
    task = SimpleNamespace(user_id=u.id)
    title, body, template = _assurance_copy(db, task, meta)
    assert "Metformin 500" in body and template == "assurance_follow_up"
    assurance = models.Notification(
        user_id=u.id, type="HEALTH", body=body, template_key="assurance_follow_up",
        context_json='{"assured_notification_id": %d}' % int(original.id), status="sent",
    )
    db.add(assurance)
    db.flush()
    opener = family_opener(db, u, assurance, language="fa", name="جواد")
    assert opener and "Metformin 500" in opener


def test_the_assurance_opener_without_a_known_subject_is_the_generic_one(db):
    u = _user(db)
    assurance = models.Notification(
        user_id=u.id, type="HEALTH", body="x", template_key="assurance_follow_up", context_json='{"assured_notification_id": 999999999}', status="sent"
    )
    db.add(assurance)
    db.flush()
    opener = family_opener(db, u, assurance, language="fa", name=None)
    assert opener == sedi_copy.t("session.origin.assurance", "fa")
