from __future__ import annotations

import re

from backend.app.services.notification_runtime import renderer


_AR_FA_RE = re.compile(r"[\u0600-\u06FF]")


def test_notification_renderer_health_alert_english_is_primary():
    out = renderer.render(
        channel="health_alert",
        language="en",
        inputs={"user_display_name": "John"},
        priority="high",
        template=None,
        user_ctx={"preferred_name": "John"},
    )
    assert out["title"] == "Health Alert"
    assert isinstance(out["body"], str) and out["body"].strip()
    assert _AR_FA_RE.search(out["title"]) is None
    assert _AR_FA_RE.search(out["body"]) is None


def test_notification_renderer_unknown_language_falls_back_to_en():
    out = renderer.render(
        channel="health_alert",
        language="fr-FR",
        inputs={"user_display_name": "John"},
        priority="high",
        template=None,
        user_ctx={"preferred_name": "John"},
    )
    assert out["title"] == "Health Alert"
    assert _AR_FA_RE.search(out["title"]) is None
    assert _AR_FA_RE.search(out["body"]) is None


def test_notification_renderer_template_texts_default_is_en():
    template = {
        "texts": {
            "fa": {"title": "سلام", "message": "حالت چطوره؟"},
            "en": {"title": "Hello", "message": "How are you?"},
            "ar": {"title": "مرحباً", "message": "كيف حالك؟"},
        }
    }
    out = renderer.render(
        channel="engagement",
        language=None,
        template=template,
        user_ctx={},  # no language in context
    )
    assert out["title"] == "Hello"
    assert out["body"].startswith("How are you")
    assert _AR_FA_RE.search(out["title"]) is None
    assert _AR_FA_RE.search(out["body"]) is None

