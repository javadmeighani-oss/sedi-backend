# backend/tests/test_notification_templates_v1.py
"""Tests for Notifications V1 templates registry and admin endpoints."""

import pytest
from backend.app.services.notification_runtime.templates_v1 import (
    get_template_v1,
    list_templates_v1,
    validate_templates_v1,
)
from backend.app.services.notification_runtime.renderer import render


def test_validate_templates_v1_returns_no_errors():
    """validate_templates_v1 returns empty list when all templates are valid."""
    errors = validate_templates_v1()
    assert errors == [], f"Expected no errors, got: {errors}"


def test_preview_render_returns_non_empty_title_body_fa():
    """Preview render for one template in fa returns non-empty title and body."""
    template = get_template_v1("companion_daily_checkin_v1")
    assert template is not None
    out = render(
        channel=template["channel"],
        language="fa",
        inputs={},
        priority=template.get("priority", "normal"),
        template=template,
    )
    assert out.get("title", "").strip(), "title should be non-empty"
    assert out.get("body", "").strip(), "body should be non-empty"


def test_preview_render_returns_non_empty_title_body_en():
    """Preview render for one template in en returns non-empty title and body."""
    template = get_template_v1("companion_daily_checkin_v1")
    assert template is not None
    out = render(
        channel=template["channel"],
        language="en",
        inputs={},
        priority=template.get("priority", "normal"),
        template=template,
    )
    assert out.get("title", "").strip(), "title should be non-empty"
    assert out.get("body", "").strip(), "body should be non-empty"


def test_renderer_works_with_template_texts_produces_title_body():
    """Renderer with template.texts produces title and body (template path)."""
    template = get_template_v1("health_alert_generic_v1")
    assert template is not None
    assert "texts" in template
    out = render(
        channel=template["channel"],
        language="en",
        inputs={},
        priority=template.get("priority", "normal"),
        template=template,
    )
    assert "title" in out and "body" in out
    assert "Health Alert" in out["title"] or "health" in out["title"].lower()
    assert len(out["body"]) > 0


def test_list_templates_v1_returns_all_keys():
    """list_templates_v1 returns at least the four V1 keys."""
    items = list_templates_v1()
    keys = [t["key"] for t in items]
    assert "companion_daily_checkin_v1" in keys
    assert "companion_encourage_move_v1" in keys
    assert "companion_breathing_break_v1" in keys
    assert "health_alert_generic_v1" in keys


def test_get_template_v1_returns_none_for_unknown():
    """get_template_v1 returns None for unknown key."""
    assert get_template_v1("nonexistent_key") is None
