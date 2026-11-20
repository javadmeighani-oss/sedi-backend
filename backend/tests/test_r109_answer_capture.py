"""DEBT-079 (R-109): on the CHAT path the interview guide steers the model, so the user's answer to Sedi's question about a complaint
is captured deterministically in I6 (medical.symptom_episodes) - no dependence on the LLM extractor flag (off by default)."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.services.care_journey import journey as j

QUESTION = "از کی شروع شده و قبلاً هم داشتی؟ فکر می‌کنی چه چیزی باعثش شده؟"


@pytest.fixture
def wrote(monkeypatch):
    from backend.app.services import candidate_promotion_service as cp
    from backend.app.services.i6 import memory_writes

    out = []
    monkeypatch.setattr(cp, "_merge_list_value", lambda db, uid, dom, key, value: [value])
    monkeypatch.setattr(memory_writes, "write_fact", lambda db, uid, dom, key, value, **k: out.append((dom, key, value)))
    return out


def test_the_answer_to_a_guide_question_about_a_complaint_is_recorded(wrote):
    assert j.record_answer(MagicMock(), 1, "از دو روز پیش شروع شده و قبلاً نداشتم", QUESTION, last_user_message="سرم خیلی درد می‌کند") is True
    assert wrote == [("medical", "symptom_episodes", ["از دو روز پیش شروع شده و قبلاً نداشتم"])]


def test_nothing_is_recorded_without_a_complaint_or_a_question(wrote):
    db = MagicMock()
    assert j.record_answer(db, 1, "از دو روز پیش", QUESTION, last_user_message="سلام، حالت چطوره") is False  # no complaint before
    assert j.record_answer(db, 1, "از دو روز پیش", "باشه، مراقب خودت باش.", last_user_message="سرم درد می‌کند") is False  # Sedi asked nothing
    assert j.record_answer(db, 1, "از دو روز پیش", QUESTION) is False  # no context at all
    assert wrote == []


def test_thanks_a_new_request_and_a_relatives_complaint_are_not_episodes(wrote):
    db = MagicMock()
    for answer in ("ممنون", "یه دکتر مغز و اعصاب پیدا کن", "مادرم هم از دیروز سردرد دارد"):
        assert j.record_answer(db, 1, answer, QUESTION, last_user_message="سرم درد می‌کند") is False, answer
    assert wrote == []


def test_the_english_complaint_flow_is_recorded_too(wrote):
    assert j.record_answer(
        MagicMock(), 1, "It started two days ago and I never had it before", "When did it start? Has it happened before?",
        last_user_message="I have a bad headache", language="en",
    ) is True and len(wrote) == 1


def test_orchestrator_passes_the_previous_user_turn(monkeypatch, wrote):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention

    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    last = SimpleNamespace(user_message="سرم خیلی درد می‌کند", sedi_response=QUESTION, created_at=datetime.utcnow())
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, **k: [last])
    orch = IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    orch.process(authenticated_user_id=42, message="از دو روز پیش شروع شده و قبلاً نداشتم", language="fa")
    assert wrote and "دو روز" in wrote[0][2][0]
