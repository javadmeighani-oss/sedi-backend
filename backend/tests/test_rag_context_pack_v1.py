# tests/test_rag_context_pack_v1.py
"""
Tests for Stage 23 Step 5 - Controlled RAG V1 (facts-anchored).
No DB required; unit tests with mocks/defensive behavior.
"""

import pytest

try:
    from backend.app.services.rag_context import (
        RagContextPack,
        build_rag_context_pack,
        is_high_risk_medical,
        rag_allowed,
        serialize_rag_pack_for_context,
    )
except ImportError:
    from app.services.rag_context import (
        RagContextPack,
        build_rag_context_pack,
        is_high_risk_medical,
        rag_allowed,
        serialize_rag_pack_for_context,
    )


# ---- build_rag_context_pack (with mock) ----

def test_build_rag_context_pack_uses_en_when_language_none(monkeypatch):
    """When UserContext fails or pack.language is None, language resolves to 'en'."""
    try:
        from backend.app.services.rag_context import rag_context_builder as builder
    except ImportError:
        from app.services.rag_context import rag_context_builder as builder

    class FailingService:
        def get_user_context(self, user_id):
            raise RuntimeError("no db")

    monkeypatch.setattr(builder, "UserContextService", lambda db: FailingService())
    pack = build_rag_context_pack(None, 1, fallback_language=None)
    assert pack.language == "en"
    assert pack.user_id == 1


def test_build_rag_context_pack_truncation_limits(monkeypatch):
    """RagContextPack has lifestyle_summary <=300, daily_summary <=200, goals <=5."""
    try:
        from backend.app.services.user_context.context_models import (
            UserContextPack,
            UserGoals,
            UserLifestyleSummary,
            QuietHours,
        )
    except ImportError:
        from app.services.user_context.context_models import (
            UserContextPack,
            UserGoals,
            UserLifestyleSummary,
            QuietHours,
        )

    long_lifestyle = "x" * 400
    long_daily = "y" * 300
    pack = UserContextPack(
        user_id=1,
        language="fa",
        goals=UserGoals(items=["a", "b", "c", "d", "e", "f", "g"]),
        lifestyle=UserLifestyleSummary(text=long_lifestyle),
        daily_memory_summary=long_daily,
        quiet_hours=QuietHours(),
    )

    class MockService:
        def get_user_context(self, user_id):
            return pack

    try:
        from backend.app.services.rag_context import rag_context_builder as builder
    except ImportError:
        from app.services.rag_context import rag_context_builder as builder
    monkeypatch.setattr(builder, "UserContextService", lambda db: MockService())

    result = build_rag_context_pack(None, 1, fallback_language="en")
    assert result.language == "fa"
    assert result.lifestyle_summary is not None
    assert len(result.lifestyle_summary) <= 300
    assert result.daily_summary is not None
    assert len(result.daily_summary) <= 200
    assert len(result.goals) <= 5


# ---- medical_risk_gate_v1 ----

def test_medical_risk_gate_detects_chest_pain_en():
    """High-risk keyword 'chest pain' in EN is detected."""
    assert is_high_risk_medical("I have chest pain", "en") is True
    assert is_high_risk_medical("something chest pain something", "en") is True


def test_medical_risk_gate_detects_suicidal_en():
    """Suicidal ideation in EN is detected."""
    assert is_high_risk_medical("I feel suicidal", "en") is True
    assert is_high_risk_medical("want to die", "en") is True


def test_medical_risk_gate_detects_stroke_en():
    """Stroke-related in EN is detected."""
    assert is_high_risk_medical("I think I'm having a stroke", "en") is True


def test_medical_risk_gate_safe_query_en():
    """Normal query in EN is not high-risk."""
    assert is_high_risk_medical("How much sleep should I get?", "en") is False
    assert is_high_risk_medical("I want to exercise more", "en") is False


def test_medical_risk_gate_fa_keywords():
    """Persian high-risk keywords are detected."""
    assert is_high_risk_medical("درد قفسه سینه", "fa") is True
    assert is_high_risk_medical("خودکشی", "fa") is True


def test_medical_risk_gate_ar_keywords():
    """Arabic high-risk keywords are detected."""
    assert is_high_risk_medical("ألم في الصدر", "ar") is True


def test_rag_allowed_false_for_high_risk():
    """rag_allowed returns False for high-risk queries."""
    assert rag_allowed("I have chest pain", "en") is False
    assert rag_allowed("خودکشی", "fa") is False


def test_rag_allowed_true_for_safe():
    """rag_allowed returns True for safe queries."""
    assert rag_allowed("What are good sleep habits?", "en") is True
    assert rag_allowed("چطور بخوابم بهتر", "fa") is True


# ---- serialize_rag_pack_for_context ----

def test_serialize_rag_pack_respects_max_chars():
    """Serialized pack is capped at max_chars."""
    pack = RagContextPack(
        user_id=1,
        language="en",
        lifestyle_summary="a" * 500,
        daily_summary="b" * 300,
        goals=["g1", "g2"],
    )
    out = serialize_rag_pack_for_context(pack, max_chars=200)
    assert len(out) <= 203  # 200 + "..."
