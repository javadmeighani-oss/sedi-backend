# tests/test_notification_renderer.py
"""
Pytest tests for Stage 16.6.4 - Notification template renderer.

Tests:
- render() returns valid {title, body, actions_json} for morning/engagement/health_alert
- Multi-language (en, fa, ar) with fallback to en
- Health alert critical adds emergency disclaimer
"""

import pytest

from backend.app.services.notification_runtime.renderer import render, DEFAULT_ACTIONS_JSON


def test_render_morning_returns_valid_for_en_fa_ar():
    """Test morning channel returns valid output for en, fa, ar."""
    for lang in ("en", "fa", "ar"):
        out = render("morning", lang, inputs={"user_display_name": "Test"})
        assert "title" in out
        assert "body" in out
        assert "actions_json" in out
        assert out["actions_json"] == DEFAULT_ACTIONS_JSON
        assert len(out["title"].strip()) > 0
        assert len(out["body"].strip()) > 0
    # en-specific check
    en_out = render("morning", "en", inputs={})
    assert "Good Morning" in en_out["title"]
    assert "dear" in en_out["body"] or "Good morning" in en_out["body"]


def test_render_engagement_with_and_without_topic():
    """Test engagement channel with optional last_topic_hint."""
    out = render("engagement", "en", inputs={})
    assert out["title"] == "Hello"
    assert len(out["body"]) > 0
    assert "actions_json" in out

    out_with_topic = render("engagement", "fa", inputs={"last_topic_hint": "sleep"})
    assert "sleep" in out_with_topic["body"]
    assert "سلام" in out_with_topic["title"]


def test_render_health_alert_critical_adds_disclaimer():
    """Test health_alert adds emergency disclaimer only when priority is critical."""
    normal_out = render("health_alert", "en", inputs={}, priority="normal")
    assert "unusual reading" in normal_out["body"].lower()
    assert "Open Sedi to review" in normal_out["body"]
    assert "seek professional" not in normal_out["body"]

    critical_out = render("health_alert", "en", inputs={}, priority="critical")
    assert "unusual reading" in critical_out["body"].lower()
    assert "seek professional" in critical_out["body"].lower()

    # fa/ar critical also include disclaimer
    fa_critical = render("health_alert", "fa", inputs={}, priority="critical")
    assert "پزشک" in fa_critical["body"] or "مراجعه" in fa_critical["body"]


def test_render_unknown_language_falls_back_to_en():
    """Test unknown language falls back to en."""
    out = render("morning", "xx", inputs={})
    assert "Good Morning" in out["title"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
