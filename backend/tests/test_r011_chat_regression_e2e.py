"""R-011 regression: a real structured-chat turn must never end in the generic processing-error message."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from backend.app.core.security import create_access_token
from backend.app.models import User

ERROR_FA = "در پردازش پیام شما خطایی رخ داد"


CAPTURED: list = []


def _fake_llm(messages):
    CAPTURED.append(messages)
    return SimpleNamespace(output_text="سلام! دربارهٔ ALS با کمال میل کمکت می‌کنم؛ از کجا شروع کنیم؟")


@pytest.fixture
def structured_user(db, monkeypatch):
    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    monkeypatch.setattr("backend.app.core.conversation.prompts.create_primary_chat_response", _fake_llm, raising=False)
    monkeypatch.setattr("backend.app.core.conversation.brain.create_primary_chat_response", _fake_llm, raising=False)
    u = User(name="Javad", secret_key="t", preferred_language="fa")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _chat(client, user, text):
    token = create_access_token({"user_id": user.id})
    return client.post(
        "/interact/chat",
        json={"user_id": user.id, "message": text},
        headers={"Accept-Language": "fa", "Authorization": f"Bearer {token}"},
    )


@pytest.mark.parametrize(
    "text",
    [
        "خوب میخواهم در مورد بیماری als بیشتر صحبت کنیم و راهکارهای مراقبتی از این بیماری را بررسی کنیم",
        "ندارم",
        "سلام صدی، چطوری؟",
        "امروز سر کار خیلی خسته شدم",
    ],
)
def test_structured_turn_never_returns_the_generic_error(client, structured_user, text, capfd):
    r = _chat(client, structured_user, text)
    out = capfd.readouterr().out
    assert r.status_code == 200, r.text
    body = r.json()
    reply = body.get("response") or body.get("message") or str(body)
    assert ERROR_FA not in reply, "BRAIN ERROR trace:\n" + "\n".join(l for l in out.splitlines() if "BRAIN ERROR" in l or "Traceback" in l or "Error" in l)[:3000]


def test_turn_with_real_user_state_never_returns_the_generic_error(client, db, monkeypatch, capfd):
    """Javad-like state: consent, earlier turns (incl. low-mood words), a DAILY summary with wellbeing signals,
    stored intake answers and a pending intake question."""
    from datetime import datetime, timedelta

    from backend.app import models
    from backend.app.services.i6.memory_writes import write_fact
    from backend.app.services.i7.hierarchy import build_daily_from_raw
    from backend.tests.test_i5_i8_lifestyle_weekly_nutrition_exercise import _seed_consent, _user

    monkeypatch.setenv("SEDI_INTELLIGENCE_ORCHESTRATOR_V1", "true")
    monkeypatch.setattr("backend.app.core.conversation.brain.create_primary_chat_response", _fake_llm, raising=False)
    monkeypatch.setattr("backend.app.core.conversation.prompts.create_primary_chat_response", _fake_llm, raising=False)
    u = _user(db, "+17770009451", tz="Asia/Tehran")
    u.preferred_language = "fa"
    u.name = "جواد"
    _seed_consent(db, u.id)
    now = datetime.utcnow()
    for i, (m, r) in enumerate(
        [
            ("امروز خیلی خسته‌ام و استرس دارم", "درکت می‌کنم."),
            ("میخوام درباره دیابت بدونم", "حتماً."),
            ("ندارم", "باشه."),
            ("میخوام یه رژیم غذایی برام بچینی", "چه غذاهایی دوست داری؟"),
        ]
    ):
        db.add(models.Memory(user_id=u.id, user_message=m, sedi_response=r, language="fa", created_at=now - timedelta(minutes=10 - i)))
    db.commit()
    try:
        write_fact(db, u.id, domain="intake", key="goal", value="سلامت بیشتر")
        write_fact(db, u.id, domain="intake", key="allergies", value="ندارم")
        db.commit()
    except Exception:
        db.rollback()
    try:
        build_daily_from_raw(db, u.id)
    except Exception:
        db.rollback()
    r = _chat(client, u, "خوب میخواهم در مورد بیماری als بیشتر صحبت کنیم و راهکارهای مراقبتی از این بیماری را بررسی کنیم")
    out = capfd.readouterr().out
    assert r.status_code == 200, r.text
    body = r.json()
    reply = body.get("response") or body.get("message") or str(body)
    trace = "\n".join(l for l in out.splitlines() if "BRAIN ERROR" in l or "Traceback" in l or "Error" in l)[:3500]
    assert ERROR_FA not in reply, "BRAIN ERROR trace:\n" + trace


def test_messages_sent_to_the_model_are_well_formed(client, db, monkeypatch):
    """Every item sent to the Responses API must be {role, content:str} with a bounded size."""
    CAPTURED.clear()
    test_turn_with_real_user_state_never_returns_the_generic_error(client, db, monkeypatch, _NoCap())
    assert CAPTURED, "model was not called"
    msgs = CAPTURED[-1]
    total = 0
    for m in msgs:
        assert set(m) <= {"role", "content"} and m["role"] in {"system", "user", "assistant"}, m.keys()
        assert isinstance(m["content"], str) and m["content"].strip(), m["role"]
        total += len(m["content"])
    print("MESSAGES:", [(m["role"], len(m["content"])) for m in msgs], "TOTAL", total)
    assert total < 60000


class _NoCap:
    def readouterr(self):
        return SimpleNamespace(out="")
