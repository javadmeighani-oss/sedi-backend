# tests/test_brain_context_injection_v1.py
"""
Tests for Stage 23 Step 3 - Brain wired to UserContextService + PersonaPolicyV1.
No external network; minimal/no DB (mocks).
"""

import pytest

try:
    from backend.app.core.conversation.prompts import build_system_prompt_with_context
    from backend.app.core.conversation.brain import _build_user_context_block, _pack_to_prompt_dict
    from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1
except ImportError:
    from app.core.conversation.prompts import build_system_prompt_with_context
    from app.core.conversation.brain import _build_user_context_block, _pack_to_prompt_dict
    from app.core.conversation.persona_policy_v1 import PersonaPolicyV1


def test_build_system_prompt_with_context_english_includes_javad():
    """With language None/EN and preferred_name Javad, prompt is English and includes 'Javad'."""
    prompt = build_system_prompt_with_context("en", "Javad", None)
    assert "Javad" in prompt
    # English markers
    assert "You are" in prompt or "female" in prompt
    en_chars = sum(1 for c in prompt if "a" <= c <= "z" or "A" <= c <= "Z")
    fa_ar = sum(1 for c in prompt if "\u0600" <= c <= "\u06FF")
    assert en_chars > fa_ar


def test_build_system_prompt_with_context_persian_includes_preferred_name():
    """With language 'fa' and preferred_name جواد, prompt includes جواد."""
    prompt = build_system_prompt_with_context("fa", "جواد", None)
    assert "جواد" in prompt


def test_build_system_prompt_with_context_appends_block():
    """context_block is appended when provided."""
    block = "[USER_CONTEXT]\nPreferred name: Test\nGoals: a, b"
    prompt = build_system_prompt_with_context("en", "Test", block)
    assert "[USER_CONTEXT]" in prompt
    assert "Preferred name: Test" in prompt
    assert "Goals: a, b" in prompt


def test_build_system_prompt_with_context_no_name_still_english():
    """With no preferred_name, prompt is still valid (English when lang en)."""
    prompt = build_system_prompt_with_context("en", None, None)
    assert prompt
    assert "female" in prompt.lower() or "Sedi" in prompt


def test_pack_to_prompt_dict_none():
    """_pack_to_prompt_dict(None) returns empty dict."""
    assert _pack_to_prompt_dict(None) == {}


def test_pack_to_prompt_dict_fake_pack():
    """_pack_to_prompt_dict with fake pack returns expected keys."""
    class FakePack:
        preferred_name = "Javad"
        language = "en"
        timezone = "UTC"
        quiet_hours = type("Q", (), {"start": "22:00", "end": "08:00"})()
        engagement_level = "normal"
        goals = type("G", (), {"items": ["sleep", "exercise"]})()
        lifestyle = type("L", (), {"text": "Active person."})()
        daily_memory_summary = "Slept well."
    d = _pack_to_prompt_dict(FakePack())
    assert d.get("preferred_name") == "Javad"
    assert d.get("language") == "en"
    assert d.get("quiet_hours", {}).get("start") == "22:00"
    assert d.get("goals_items") == ["sleep", "exercise"]
    assert d.get("lifestyle_text") == "Active person."
    assert d.get("daily_memory_summary") == "Slept well."


def test_build_user_context_block_none():
    """_build_user_context_block(None) returns empty string."""
    assert _build_user_context_block(None) == ""


def test_build_user_context_block_with_preferred_name_and_goals():
    """Context block includes preferred name and goals (max ~8 lines)."""
    class FakePack:
        preferred_name = "Javad"
        goals = type("G", (), {"items": ["exercise", "sleep"]})()
        lifestyle = type("L", (), {"text": None})()
    block = _build_user_context_block(FakePack())
    assert "[USER_CONTEXT]" in block
    assert "Javad" in block
    assert "exercise" in block or "Goals" in block


def test_system_prompt_with_context_block_contains_both_persona_and_javad():
    """build_system_prompt_with_context with preferred_name and context block yields both persona and name."""
    context_block = "[USER_CONTEXT]\nPreferred name: Javad\nGoals: exercise"
    prompt = build_system_prompt_with_context("en", "Javad", context_block)
    assert "Javad" in prompt
    assert "[USER_CONTEXT]" in prompt
    assert "female" in prompt.lower() or "Sedi" in prompt
    assert "Goals" in prompt or "exercise" in prompt
