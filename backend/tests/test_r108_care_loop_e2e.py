"""R-108 / R-074 step 2 - the CARE LOOP end to end on a REAL database session (in-memory SQLite, only the tables the loop touches).

Proof that Sedi's brain stores what happens and the rest of the system reads it back:
  complaint -> intake interview + hours-level follow-up chain (I10) -> the user's answer -> I6 episode -> CareState reads it (issue +
  acute follow-up + one summary line) -> the status report sees the same picture -> a raw chat turn is recalled in chat (I7) ->
  «it got better» -> the chain closes, I7 user_done is recorded, CareState shows the issue improving and one resolved journey ->
  and the revoked-consent / worse / no-consent branches.
No owner is stubbed: the consent gate, I6 writer, I10 task rows, user_done ledger, raw memory and recall all run for real.
"""
import contextlib
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import models, sedi_copy
from backend.app.database import Base
from backend.app.services import care_state as cs
from backend.app.services.care_journey import journey as j
from backend.app.services.i6 import consent_service as consent
from backend.app.services.status_report import builder as report

TABLES = (
    "users", "user_consents", "user_consent_scopes", "user_memory_facts", "memory", "care_follow_up_tasks", "user_events",
    "interaction_events", "user_medications", "medications", "user_medication_schedules", "notifications", "user_doctors",
    "daily_memory_summaries", "user_period_summaries", "user_lifelong_profiles", "user_memory_export_jobs", "user_profile_core", "user_profile_facts",
)
REQUEST = "یه دکتر قلب در شهر پردیس معرفی کن"


@pytest.fixture(autouse=True)
def _fixed_timezone(monkeypatch):
    """The timezone resolver inspects the schema through a second connection; on the SINGLE shared in-memory SQLite connection that
    inspection resets the open transaction (a harness artifact - PostgreSQL uses separate connections). The zone is not what the
    loop is about, so it is pinned."""
    from backend.app.services.gate4 import policy_prefs_bridge

    monkeypatch.setattr(policy_prefs_bridge, "resolve_validated_user_timezone", lambda db, user_id: "Asia/Tehran")


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    Base.metadata.create_all(engine, tables=[Base.metadata.tables[t] for t in TABLES])
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    # pysqlite cannot nest SAVEPOINTs reliably (PostgreSQL in CI can); the loop under test only needs the happy path, so a
    # nested transaction is a plain no-op block here.
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


def _interview():
    return sedi_copy.t("journey.intake.lead", "fa") + "\n\n" + sedi_copy.t("journey.interview.chest", "fa")


# --- the loop ----------------------------------------------------------------------------------------------------------------------------------
def test_the_whole_care_loop_runs_through_the_brain(db, user):
    uid = user.id
    # 0. nothing is known yet
    assert cs.get_care_state(db, uid).is_empty and cs.summary_line(cs.get_care_state(db, uid), "fa") == ""

    # 1. a heart-doctor request: the interview comes BEFORE the introduction and the follow-up chain is tracked from this moment (I10)
    intake = j.intake_message(db, uid, REQUEST, "fa", intake_done=False)
    assert intake and j.is_interview_reply(intake)
    state = cs.get_care_state(db, uid)
    assert state.has_open_journey and state.is_acute and state.follow_ups[0].next_due is not None
    assert state.follow_ups[0].next_due > datetime.utcnow()  # hours ahead, never in the past

    # 2. the user's answer becomes an I6 episode (deterministic, consent-gated)
    assert j.record_answer(db, uid, "از دو روز پیش شروع شده و قبلاً نداشتم", _interview()) is True
    state = cs.get_care_state(db, uid)
    assert [i.status for i in state.issues] == ["open"] and "دو روز" in state.issues[0].text

    # 3. ONE deterministic line carries the picture for chat / notifications
    line = cs.summary_line(state, "fa")
    assert "موضوع باز" in line and "دو روز" in line and sedi_copy.t("care_state.followup", "fa") in line

    # 4. the status report reads the SAME picture (timeline + active follow-up)
    sections = {s["key"]: [x["text"] for x in s["lines"]] for s in report.build_status_report(db, uid, "doctor_visit", "fa")["sections"]}
    assert any("دو روز" in t for t in sections["reason"]) and sections["follow_up"] == [sedi_copy.t("report.followup.open", "fa")]
    assert sections["timeline"] == ["از دو روز پیش شروع شده و قبلاً نداشتم"]

    # 5. «it got better»: the chain closes, I7 user_done is written, the issue shows improving, one resolved journey
    assert j.apply_status(db, uid, "الان بهترم", "fa") == "better"
    state = cs.get_care_state(db, uid)
    assert not state.has_open_journey and state.resolved_recent == 1 and state.issues[0].status == "better"
    assert db.query(models.InteractionEvent).filter(models.InteractionEvent.user_id == uid).count() >= 1  # the ledger remembers it
    assert "رو به بهبود" in cs.summary_line(state, "fa")
    assert "this week" not in cs.summary_line(state, "fa")


def test_the_chat_turn_is_stored_raw_and_recalled(db, user):
    from backend.app.core.conversation.memory import ConversationMemory
    from backend.app.services.i7.recall import build_recall_block

    memory = ConversationMemory(db)
    assert memory.save_conversation(user.id, "از سردرد صبحگاهی رنج می‌برم", "بیشتر بگو", "fa") is not None  # passed the consent gate
    for n in range(11):  # recall skips the latest 10 turns (they are already in the model's recent history)
        memory.save_conversation(user.id, f"پیام عادی شماره {n} درباره موضوع دیگری", f"پاسخ {n}", "fa")
    block = build_recall_block(db, user.id, "دوباره سردرد دارم", "fa")
    assert block and "سردرد صبحگاهی" in block  # the user's own earlier words come back, with their day


def test_worse_replaces_the_chain_with_an_acute_one(db, user):
    uid = user.id
    j.intake_message(db, uid, "یه دکتر پوست در شهر شیراز معرفی کن", "fa", intake_done=False)  # a routine journey
    assert cs.get_care_state(db, uid).follow_ups[0].tier == "routine"
    assert j.record_answer(db, uid, "از دو روز پیش پوستم می‌خارد", sedi_copy.t("journey.interview.generic", "fa")) is True
    assert j.apply_status(db, uid, "بدتر شدم", "fa") == "worse"
    state = cs.get_care_state(db, uid)
    assert state.is_acute and len(state.follow_ups) == 1  # the old chain is replaced, not duplicated
    notes = report._facts(db, uid)[("medical", "symptom_episodes")]
    assert notes[-1].startswith(sedi_copy.t("journey.status_note.worse", "fa") + " · ")
    assert state.issues[0].status == "worse"


def test_without_consent_nothing_is_read_and_nothing_is_tracked(db):
    row = models.User(name="بی‌رضایت", secret_key="x", preferred_language="fa")
    db.add(row)
    db.commit()
    assert j.intake_message(db, row.id, REQUEST, "fa", intake_done=False) is None  # no memory-write consent: nothing is asked or promised
    state = cs.get_care_state(db, row.id)
    assert state.consent is False and state.is_empty and cs.summary_line(state, "fa") == ""
    assert report.build_status_report(db, row.id, "doctor_visit", "fa")["state"] == "no_consent"


def test_revoking_consent_hides_the_picture_again(db, user):
    uid = user.id
    j.intake_message(db, uid, REQUEST, "fa", intake_done=False)
    assert cs.get_care_state(db, uid).has_open_journey
    consent.revoke_memory_consent(db, uid)
    state = cs.get_care_state(db, uid)
    assert state.consent is False and not state.follow_ups  # the gate closes the read, whatever is stored


def test_appointments_and_medicines_are_part_of_the_picture(db, user):
    uid = user.id
    soon = datetime.utcnow() + timedelta(days=1)
    db.add_all([
        models.UserEvent(user_id=uid, title="ملاقات دکتر قلب", starts_at=soon, status="scheduled"),
        models.UserEvent(user_id=uid, title="قدیمی", starts_at=datetime.utcnow() - timedelta(days=3), status="scheduled"),
        models.UserEvent(user_id=uid, title="لغوشده", starts_at=soon, status="cancelled"),
    ])
    db.commit()
    state = cs.get_care_state(db, uid)
    assert [e.title for e in state.events] == ["ملاقات دکتر قلب"]  # only the next scheduled one, never past or cancelled
    assert "نوبت پیش‌رو: ملاقات دکتر قلب" in cs.summary_line(state, "fa")
    assert state.medications == 0


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_summary_line_exists_in_every_language(db, user, lang):
    j.intake_message(db, user.id, REQUEST, lang, intake_done=False)
    j.record_answer(db, user.id, "since two days ago and never before", sedi_copy.t("journey.interview.chest", lang), language="en")
    line = cs.summary_line(cs.get_care_state(db, user.id), lang)
    assert line and "{" not in line
