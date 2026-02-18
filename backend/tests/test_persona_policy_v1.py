# tests/test_persona_policy_v1.py
"""
Tests for Stage 23 Step 2 - Persona Policy v1 (unified persona, EN canonical, fa/ar variants).
No DB required.
"""

import pytest

try:
    from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1, PersonaPolicyConfig
except ImportError:
    from backend.app.core.conversation.persona_policy_v1 import PersonaPolicyV1, PersonaPolicyConfig


def test_default_language_is_english_when_none():
    """PersonaPolicyV1.system_prompt(None, None) contains English markers and does NOT look Persian/Arabic."""
    prompt = PersonaPolicyV1.system_prompt(None, None)
    assert prompt
    # English markers
    assert "Sedi" in prompt or "female" in prompt
    assert "You are" in prompt or "You " in prompt
    # Should not be primarily Persian/Arabic script
    fa_ar_chars = sum(1 for c in prompt if "\u0600" <= c <= "\u06FF" or "\u0750" <= c <= "\u077F")
    en_chars = sum(1 for c in prompt if "a" <= c <= "z" or "A" <= c <= "Z")
    assert en_chars > fa_ar_chars, "Default (None) should yield English prompt"


def test_english_contains_female_and_not_doctor():
    """Prompt contains 'female' and 'not a doctor' (or equivalent short phrase)."""
    prompt = PersonaPolicyV1.system_prompt("en", None)
    assert "female" in prompt.lower()
    assert "not a doctor" in prompt.lower() or "do not diagnose" in prompt.lower()


def test_persian_variant_is_present_and_human():
    """PersonaPolicyV1.system_prompt('fa', {'preferred_name':'جواد'}) includes 'جواد' and has a natural Persian intro."""
    prompt = PersonaPolicyV1.system_prompt("fa", {"preferred_name": "جواد"})
    assert "جواد" in prompt
    # Natural Persian intro (Sedi identity in Persian)
    assert "سدی" in prompt or "صدی" in prompt or "تو " in prompt
    assert prompt.strip()


def test_arabic_variant_is_present():
    """PersonaPolicyV1.system_prompt('ar', None) includes assistant name and is non-empty."""
    prompt = PersonaPolicyV1.system_prompt("ar", None)
    assert prompt
    # Arabic script present; assistant reference
    assert "سدي" in prompt or "صدي" in prompt or "أنت" in prompt


def test_locale_prefix_resolution():
    """'fa-IR' -> Persian, 'en-US' -> English, 'ar-SA' -> Arabic."""
    assert PersonaPolicyV1.resolve_language("fa-IR") == "fa"
    assert PersonaPolicyV1.resolve_language("en-US") == "en"
    assert PersonaPolicyV1.resolve_language("ar-SA") == "ar"
    assert PersonaPolicyV1.resolve_language("fa") == "fa"
    assert PersonaPolicyV1.resolve_language("en") == "en"
    assert PersonaPolicyV1.resolve_language("ar") == "ar"
    assert PersonaPolicyV1.resolve_language("") == "en"
    assert PersonaPolicyV1.resolve_language(None) == "en"


def test_style_guide_returns_non_empty():
    """style_guide returns short string for en/fa/ar."""
    for lang in ("en", "fa", "ar", None):
        guide = PersonaPolicyV1.style_guide(lang)
        assert isinstance(guide, str)
        assert len(guide) > 0


def test_safety_rules_list():
    """safety_rules returns a non-empty list."""
    rules = PersonaPolicyV1.safety_rules("en")
    assert isinstance(rules, list)
    assert len(rules) >= 1


def test_proactive_rules_list():
    """proactive_rules returns a non-empty list."""
    rules = PersonaPolicyV1.proactive_rules("en")
    assert isinstance(rules, list)
    assert len(rules) >= 1


def test_config_defaults():
    """PersonaPolicyConfig has expected defaults."""
    cfg = PersonaPolicyConfig()
    assert cfg.assistant_name == "Sedi"
    assert cfg.assistant_gender == "female"
    assert cfg.canonical_language == "en"
    assert "human" in cfg.tone_tags
    assert cfg.medical_safety_mode == "care_companion"


def test_build_system_prompt_v1_integration():
    """build_system_prompt_v1 returns same as PersonaPolicyV1.system_prompt."""
    try:
        from backend.app.core.conversation.prompts import build_system_prompt_v1
    except ImportError:
        from backend.app.core.conversation.prompts import build_system_prompt_v1
    out = build_system_prompt_v1("en", None)
    assert out == PersonaPolicyV1.system_prompt("en", None)
    assert "female" in out.lower()
