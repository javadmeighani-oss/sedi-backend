"""Javad 2026-10-29: «صدی در بخش I7 باید توانایی ثبت تمام چت‌ها را داشته باشد».

Turns answered WITHOUT the language model (reminder confirmations and clarifications, directory/plan replies, terminal
safety) never reached ConversationMemory.save_conversation - only the generative path (brain) did - so they were missing
from My History, the same-day recap, the daily summary and the reminder continuation. The orchestrator now records them
(consent-gated, fail-open, the user's ORIGINAL words)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

os.environ.setdefault("SMS_DISABLED", "true")

from backend.app import models
from backend.app.models import User, UserProfileCore
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
from backend.app.services.intelligence.safety_risk import assess_safety_risk_safe


def _user(db, phone: str) -> User:
    u = User(name="RecU", secret_key="t", preferred_language="fa", phone=phone)
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(UserProfileCore(user_id=u.id, timezone="UTC"))
    db.commit()
    return u


def _turns(db, user_id: int):
    return db.query(models.Memory).filter(models.Memory.user_id == user_id).order_by(models.Memory.id).all()


def test_a_reminder_confirmation_turn_is_recorded(client, db):
    u = _user(db, "+19990070001")
    grant_memory_consent(db, u.id, commit=True)
    msg = "Tomorrow at 10 I have an exam. Remind me 1 hour before."
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    res = orch.process(
        authenticated_user_id=u.id,
        message=msg,
        language="en",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(message=msg, language="en"),
    )
    rows = _turns(db, u.id)
    assert len(rows) == 1, "a deterministic (no-LLM) turn must be stored in I7"
    assert rows[0].user_message == msg  # the user's own words
    assert rows[0].sedi_response == res.message  # exactly what Sedi said
    assert rows[0].durable_write is True


def test_b_clarification_turn_is_recorded_with_the_original_words(client, db):
    u = _user(db, "+19990070002")
    grant_memory_consent(db, u.id, commit=True)
    msg = "یادم بنداز"  # no time: Sedi asks when
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    res = orch.process(
        authenticated_user_id=u.id,
        message=msg,
        language="fa",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(message=msg, language="fa"),
    )
    rows = _turns(db, u.id)
    assert len(rows) == 1
    assert rows[0].user_message == msg
    assert rows[0].sedi_response == res.message and res.message.strip()


def test_c_the_followup_answer_continues_because_the_question_was_recorded(client, db):
    """The reminder continuation reads Sedi's own question from I7 - it only works if that turn was stored."""
    u = _user(db, "+19990070003")
    grant_memory_consent(db, u.id, commit=True)
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    first = "یادم بنداز"
    orch.process(
        authenticated_user_id=u.id,
        message=first,
        language="fa",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(message=first, language="fa"),
    )
    orch._reminder_timezone = lambda ctx, user_id: "UTC"
    cont = orch._continue_reminder_clarification(None, u.id, "۵ دقیقه دیگه", "fa")
    assert cont.startswith("یادم بنداز"), cont


def test_d_no_consent_means_no_record(client, db):
    u = _user(db, "+19990070004")  # memory consent never granted
    msg = "Tomorrow at 10 I have an exam. Remind me 1 hour before."
    orch = IntelligenceOrchestrator(db=db, structured_mode=False)
    orch.process(
        authenticated_user_id=u.id,
        message=msg,
        language="en",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(message=msg, language="en"),
    )
    assert _turns(db, u.id) == []


def test_e_an_ordinary_llm_turn_is_still_recorded_exactly_once(client, db):
    u = _user(db, "+19990070005")
    grant_memory_consent(db, u.id, commit=True)

    def _stub_gen(*_a, **_k):
        from backend.app.core.conversation.memory import ConversationMemory

        mem = ConversationMemory(db).save_conversation(u.id, "hello there", "Hello — ordinary chat stub.", "en")
        return {"message": "Hello — ordinary chat stub.", "durable_memory_id": mem.id}

    orch = IntelligenceOrchestrator(db=db, structured_mode=False, legacy_generator=_stub_gen)
    orch.process(
        authenticated_user_id=u.id,
        message="hello there",
        language="en",
        timezone="UTC",
        precomputed_assessment=assess_safety_risk_safe(message="hello there", language="en"),
    )
    assert len(_turns(db, u.id)) == 1  # the generative path is not double-written
