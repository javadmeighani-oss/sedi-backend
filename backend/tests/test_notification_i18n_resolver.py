# backend/tests/test_notification_i18n_resolver.py
"""Tests for multi-language notification text resolution (i18n_resolver)."""

import pytest
from backend.app.services.notification_runtime.i18n_resolver import (
    resolve_text_by_user_language,
)


def test_exact_match_selects_fa():
    """user_language='fa' selects fa block."""
    texts = {
        "fa": {"title": "عنوان", "message": "پیام"},
        "en": {"title": "Title", "message": "Message"},
    }
    out = resolve_text_by_user_language(texts, "fa", default="fa")
    assert out["title"] == "عنوان"
    assert out["message"] == "پیام"
    assert out.get("body") == "پیام"


def test_prefix_match_fa_ir_selects_fa():
    """user_language='fa-IR' selects fa block (prefix match)."""
    texts = {
        "fa": {"title": "عنوان", "message": "پیام"},
        "en": {"title": "Title", "message": "Message"},
    }
    out = resolve_text_by_user_language(texts, "fa-IR", default="fa")
    assert out["title"] == "عنوان"
    assert out["message"] == "پیام"


def test_fallback_to_default_when_user_language_none():
    """user_language=None selects default (fa) if present."""
    texts = {
        "fa": {"title": "عنوان", "message": "پیام"},
        "en": {"title": "Title", "message": "Message"},
    }
    out = resolve_text_by_user_language(texts, None, default="fa")
    assert out["title"] == "عنوان"
    assert out["message"] == "پیام"


def test_fallback_to_en_when_fa_missing():
    """Fallback to en when fa missing."""
    texts = {
        "en": {"title": "Title", "message": "Message"},
        "ar": {"title": "عنوان", "message": "رسالة"},
    }
    out = resolve_text_by_user_language(texts, "fa", default="fa")
    assert out["title"] == "Title"
    assert out["message"] == "Message"


def test_flat_structure_passthrough():
    """Flat {'title': '...', 'message': '...'} returns unchanged."""
    flat = {"title": "Hello", "message": "World"}
    out = resolve_text_by_user_language(flat, "fa", default="fa")
    assert out == {"title": "Hello", "message": "World"}


def test_weird_input_safe():
    """Weird input returns {} or safe dict, no exception."""
    assert resolve_text_by_user_language(None, "fa") == {}
    assert resolve_text_by_user_language([], "fa") == {}
    assert resolve_text_by_user_language("not a dict", "fa") == {}
    assert resolve_text_by_user_language({}, "fa") == {}
    # Multilingual but no valid block
    assert resolve_text_by_user_language({"fa": [], "en": 1}, "fa") == {}
    # Nested empty
    out = resolve_text_by_user_language({"fa": {}}, "fa")
    assert out == {}
