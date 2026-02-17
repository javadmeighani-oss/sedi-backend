"""
Unit tests: KC Companion Tone Layer V1.
- Policy/fatigue logic unchanged (no_question when blocked).
- confirm_candidate responses have display_* fields and tone_version.
- lang query param switches copy (fa/en).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root (folder containing backend/) for backend.app
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.knowledge.tone.companion_v1 import apply_companion_tone
from backend.app.services.knowledge.question_engine import _format_confirm_question, _value_to_display


# --- Tone layer in isolation ---

def test_apply_companion_tone_adds_display_fields():
    """confirm_candidate payload gets display_title, display_body, display_choices, tone_version, ui_hints."""
    raw = {
        "user_id": 1,
        "question_id": "kc_q_confirm_candidate_v1",
        "question_type": "confirm_candidate",
        "field_key": "medications",
        "candidate_id": 10,
        "text": "درست متوجه شدم داروی «متفورمین» مصرف می‌کنید؟",
        "options": ["بله، درسته", "نه"],
        "reason": "تایید اطلاعات استخراج‌شده از گفتگو.",
    }
    out = apply_companion_tone(raw, lang="fa")
    assert out["display_title"]
    assert out["display_body"]
    assert out["tone_version"] == "companion_v1"
    assert out["ui_hints"] == {"style": "companion", "compact": True}
    assert isinstance(out["display_choices"], list)
    assert len(out["display_choices"]) >= 2
    accept = next((c for c in out["display_choices"] if c.get("key") == "accept"), None)
    reject = next((c for c in out["display_choices"] if c.get("key") == "reject"), None)
    assert accept and accept.get("label")
    assert reject and reject.get("label")
    # Original fields kept
    assert out["question_type"] == "confirm_candidate"
    assert out["candidate_id"] == 10
    assert out["text"] == raw["text"]


def test_apply_companion_tone_lang_en():
    """lang=en yields English display_title and choice labels."""
    raw = {
        "question_type": "confirm_candidate",
        "text": "درست متوجه شدم داروی «متفورمین» مصرف می‌کنید؟",
        "options": ["بله، درسته", "نه"],
    }
    out = apply_companion_tone(raw, lang="en")
    assert out["tone_version"] == "companion_v1"
    assert "Quick question" in out["display_title"] or out["display_title"] == "Quick question"
    labels = [c["label"] for c in out["display_choices"]]
    assert any("Yes" in l or "yes" in l.lower() for l in labels)
    assert any("No" in l or "skip" in l.lower() or "Skip" in l for l in labels)


def test_apply_companion_tone_lang_fa():
    """lang=fa yields Persian display_title and choice labels."""
    raw = {
        "question_type": "confirm_candidate",
        "text": "درست متوجه شدم داروی «متفورمین» مصرف می‌کنید؟",
        "options": ["بله، درسته", "نه"],
    }
    out = apply_companion_tone(raw, lang="fa")
    assert out["display_title"]
    assert out["display_choices"][0]["key"] == "accept"
    assert out["display_choices"][1]["key"] == "reject"
    # FA labels
    assert "بله" in out["display_choices"][0]["label"] or "درسته" in out["display_choices"][0]["label"]
    assert "نه" in out["display_choices"][1]["label"] or "رد" in out["display_choices"][1]["label"]


def test_weak_extraction_fallback_fa():
    """When extracted value is «هم» (stopword), display_body uses gentle fallback in FA."""
    raw = {
        "question_type": "confirm_candidate",
        "text": "درست متوجه شدم داروی «هم» مصرف می‌کنید؟",
        "options": ["بله، درسته", "نه"],
    }
    out = apply_companion_tone(raw, lang="fa")
    assert out["tone_version"] == "companion_v1"
    # Fallback body (دقیق نیست / ردش کن)
    assert "دقیق نیست" in out["display_body"] or "ردش کن" in out["display_body"] or "دوباره بپرسم" in out["display_body"]
    assert out["display_choices"][0]["key"] == "accept"
    assert out["display_choices"][1]["key"] == "reject"


def test_weak_extraction_short_value():
    """Extracted value length < 2 triggers fallback."""
    raw = {
        "question_type": "confirm_candidate",
        "text": "درست متوجه شدم داروی «ا» مصرف می‌کنید؟",
        "options": ["بله، درسته", "نه"],
    }
    out = apply_companion_tone(raw, lang="fa")
    assert "دقیق نیست" in out["display_body"] or "ردش کن" in out["display_body"] or "دوباره بپرسم" in out["display_body"]


def test_non_confirm_candidate_unchanged_by_tone():
    """apply_companion_tone is only called for confirm_candidate in router; tone layer still adds fields if called."""
    raw = {
        "question_type": "profile_question",
        "question_id": "kc_q_birth_year_v1",
        "text": "چه سالی به دنیا آمدی؟",
        "options": [],
    }
    out = apply_companion_tone(raw, lang="fa")
    assert out["display_title"]
    assert out["display_body"]
    assert out["tone_version"] == "companion_v1"
    assert out["question_type"] == "profile_question"


def test_confirm_question_value_json_dict_renders_display_value():
    """value_json='{"value":"Vitamin D"}' renders as 'Vitamin D' in text, not dict repr."""
    from types import SimpleNamespace
    cand = SimpleNamespace(value_json='{"value":"Vitamin D"}', fact_type="medications")
    text = _format_confirm_question(cand)
    assert "Vitamin D" in text
    assert "{'value':" not in text


def test_value_to_display_dict_value_key():
    """_value_to_display extracts value from dict for template."""
    assert _value_to_display({"value": "Vitamin D"}) == "Vitamin D"
    assert _value_to_display({"value": 42}) == "42"
    assert _value_to_display({"name": "Foo"}) == "Foo"
    assert _value_to_display("plain") == "plain"


# --- API-level: policy unchanged, display_* and lang param ---

@pytest.fixture()
def _api_client():
    from starlette.testclient import TestClient
    from backend.app.main import app as sedi_app
    return TestClient(sedi_app)


@pytest.fixture()
def _api_db():
    from backend.app.database import Base, SessionLocal, engine
    from sqlalchemy.orm import Session
    Base.metadata.create_all(bind=engine)
    session = next(SessionLocal())
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def _api_user_id(_api_db):
    from sqlalchemy import text
    uid = 91010
    _api_db.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, NOW())"
        ),
        {"id": uid, "name": "Tone Test", "secret": "z", "lang": "fa"},
    )
    _api_db.commit()
    return uid


def test_next_question_fatigue_still_no_question(_api_client, _api_user_id, monkeypatch):
    """Policy unchanged: when blocked by fatigue_control, response is still no_question."""
    monkeypatch.setenv("KC_DAILY_QUESTION_CAP", "0")
    r = _api_client.get(f"/knowledge/next_question?user_id={_api_user_id}")
    assert r.status_code == 200, r.text
    data = r.json().get("data")
    assert data is not None
    assert data.get("status") == "no_question"
    assert data.get("reason") == "fatigue_control"


def test_next_question_confirm_candidate_has_display_fields_and_lang(_api_client, _api_user_id, monkeypatch):
    """When confirm_candidate is returned, display_* and tone_version exist; lang=en yields English copy."""
    import uuid
    monkeypatch.setenv("KC_COOLDOWN_MINUTES", "0")
    monkeypatch.setenv("KC_BURST_GUARD_MINUTES", "0")
    # Seed candidate
    _api_client.post(
        "/knowledge/extract_from_message",
        json={
            "user_id": _api_user_id,
            "text": "دارم متفورمین می‌خورم",
            "language": "fa",
            "source_message_id": f"pytest-tone-{uuid.uuid4().hex[:12]}",
        },
    )
    r = _api_client.get(f"/knowledge/next_question?user_id={_api_user_id}&lang=en")
    assert r.status_code == 200, r.text
    data = r.json().get("data")
    assert data is not None, "expected a question"
    assert data.get("question_type") == "confirm_candidate"
    assert data.get("display_title"), "display_title required"
    assert data.get("display_body"), "display_body required"
    assert data.get("tone_version") == "companion_v1"
    assert data.get("ui_hints", {}).get("style") == "companion"
    assert isinstance(data.get("display_choices"), list) and len(data["display_choices"]) >= 2
    # lang=en -> English
    assert "Quick question" in data["display_title"] or data["display_title"] == "Quick question"
