"""R-088 A1 v2 through the REAL orchestrator (Codex P2, PR 185): «just remind me» / «فقط یادم بنداز» answers an open pill
interview. The intent registry reads it as a reminder WITHOUT a time, so the generic clarification already set skip_generator;
the interview must still reach its safe escape and create the reminder at the time given earlier. DB-free (MagicMock session)."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.medication_care import chat_reminder as mc

REQUEST = "هر روز ساعت ۲ بعدازظهر یادم بنداز قرص بخورم"


def _orch(monkeypatch, rows, created):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    monkeypatch.setattr(mc, "history_available", lambda db, uid: True)
    monkeypatch.setattr(mc, "_recent_turns", lambda db, uid, now: rows)

    def fake_create(db, *, user_id, draft, language, timezone_name, name, message=None):
        created.append(name)
        return {"kind": "medication", "created": True, "duplicate": False, "name": name or mc.provisional_name(language),
                "named": bool(name), "time": "14:00", "days": None}

    monkeypatch.setattr(mc, "_create", fake_create)
    called = {"gen": False}

    def gen(*a, **k):
        called["gen"] = True
        return {"message": "GENERIC", "detected_name": None}

    return IntelligenceOrchestrator(db=MagicMock(), legacy_generator=gen, structured_mode=False), called


def _rows(stage_reply):
    now = datetime.utcnow()
    return [
        SimpleNamespace(user_message="لووتیروکسین", sedi_response=stage_reply, created_at=now),
        SimpleNamespace(user_message=REQUEST, sedi_response=sedi_copy.t("medication.chat.q.ask_name", "fa"), created_at=now),
    ]


@pytest.mark.parametrize("answer", ["فقط یادم بنداز", "همین ساعت", "بدون سوال"])
def test_an_insistence_reply_creates_the_reminder_through_the_orchestrator(monkeypatch, answer):
    created = []
    orch, called = _orch(monkeypatch, _rows(sedi_copy.t("medication.chat.q.ask_reason", "fa", name="لووتیروکسین")), created)
    out = orch.process(authenticated_user_id=42, message=answer, language="fa")
    assert created == ["لووتیروکسین"], (answer, out.message, out.reason_codes)
    assert "14:00" in out.message and called["gen"] is False
    assert "R088_MEDICATION_INTERVIEW_STEP" in out.reason_codes
