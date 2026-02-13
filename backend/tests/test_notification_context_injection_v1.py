# tests/test_notification_context_injection_v1.py
"""
Tests for Stage 23 Step 4 - Notification context injection (UserContextPack personalization).
No DB required; unit tests with mocks.
"""

import pytest

try:
    from backend.app.services.notification_runtime.renderer import (
        render,
        _personalize_text,
        _one_goals_lifestyle_hint,
        _append_goals_hint,
    )
    from backend.app.services.notification_runtime.user_context_adapter import build_notification_context
except ImportError:
    from app.services.notification_runtime.renderer import (
        render,
        _personalize_text,
        _one_goals_lifestyle_hint,
        _append_goals_hint,
    )
    from app.services.notification_runtime.user_context_adapter import build_notification_context


# ---- _personalize_text ----

def test_personalize_text_en_preferred_name_adds_hey():
    """EN + preferred_name prepends 'Hey {name}, '."""
    out = _personalize_text("Quick check-in — how are you?", "en", {"preferred_name": "Javad"}, True, "Javad")
    assert "Javad" in out
    assert out.startswith("Hey Javad,") or "Hey Javad," in out


def test_personalize_text_fa_preferred_name_adds_jan_style():
    """FA + preferred_name adds جان style."""
    out = _personalize_text("همه چی خوبه؟", "fa", {"preferred_name": "جواد"}, True, "جواد")
    assert "جواد" in out
    assert "جان" in out


def test_personalize_text_ar_adds_ya():
    """AR + preferred_name adds يا."""
    out = _personalize_text("هل كل شيء على ما يرام؟", "ar", {"preferred_name": "Ahmad"}, True, "Ahmad")
    assert "Ahmad" in out
    assert "يا" in out or "يا " in out


def test_personalize_text_no_preferred_name_unchanged():
    """No preferred_name -> body unchanged (except optional hint)."""
    body = "Quick check-in — how are you?"
    out = _personalize_text(body, "en", {}, True, None)
    assert out == body or out.startswith(body)


def test_personalize_text_non_companion_unchanged():
    """Non-companion channel -> text unchanged."""
    body = "An unusual reading was detected."
    out = _personalize_text(body, "en", {"preferred_name": "Javad"}, False, "Javad")
    assert out == body


def test_personalize_text_empty_ctx_companion_unchanged():
    """Companion but empty user_ctx -> no name prepended."""
    body = "Hello, how are you?"
    out = _personalize_text(body, "en", {}, True, None)
    assert "Hey" not in out or out == body


# ---- goals/lifestyle hint ----

def test_one_goals_lifestyle_hint_en_goals():
    """EN + goals_items returns short supportive clause."""
    out = _one_goals_lifestyle_hint("en", {"goals_items": ["sleep better", "exercise"]})
    assert out
    assert "goal" in out.lower() or "step" in out.lower()


def test_one_goals_lifestyle_hint_fa_goals():
    """FA + goals_items returns Persian hint."""
    out = _one_goals_lifestyle_hint("fa", {"goals_items": ["خواب بهتر"]})
    assert out
    assert "قدم" in out or "هدفت" in out or "موثره" in out


def test_one_goals_lifestyle_hint_empty_returns_empty():
    """No goals or lifestyle -> empty string."""
    assert _one_goals_lifestyle_hint("en", {}) == ""
    assert _one_goals_lifestyle_hint("en", {"goals_items": []}) == ""


def test_append_goals_hint_non_companion_unchanged():
    """_append_goals_hint for health_alert leaves body unchanged."""
    body = "An unusual reading was detected."
    out = _append_goals_hint(body, "en", {"goals_items": ["sleep"]}, False)
    assert out == body


def test_append_goals_hint_companion_with_goals_appends():
    """Companion + goals_items appends short hint."""
    body = "Hello, how are you?"
    out = _append_goals_hint(body, "en", {"goals_items": ["sleep"]}, True)
    assert out.startswith(body)
    assert len(out) > len(body)


# ---- render() with user_ctx ----

def test_render_companion_with_user_ctx_preferred_name():
    """render(companion, ..., user_ctx={preferred_name}) yields body with name."""
    result = render(
        channel="companion",
        language="en",
        inputs={},
        priority="normal",
        template={
            "channel": "companion",
            "texts": {
                "en": {"title": "Hello", "message": "Just checking in — how are you? 🌿"},
            },
        },
        user_ctx={"preferred_name": "Javad"},
    )
    assert result.get("body")
    assert "Javad" in result.get("body", "")


def test_render_health_alert_user_ctx_no_goals_in_body():
    """health_alert with user_ctx does not add goals/lifestyle hint (companion-only)."""
    result = render(
        channel="health_alert",
        language="en",
        inputs={},
        priority="high",
        user_ctx={"preferred_name": "Javad", "goals_items": ["sleep"]},
    )
    body = result.get("body", "")
    assert "An unusual reading" in body or "detected" in body
    # Goals hint is only for companion; health_alert body stays conservative
    assert "goal" not in body.lower() or "Open Sedi" in body


def test_render_no_user_ctx_unchanged_behavior():
    """render without user_ctx still returns title/body (backward compatible)."""
    result = render("engagement", "en", {}, "normal", user_ctx=None)
    assert "title" in result and "body" in result
    assert result["title"]
    assert result["body"]


# ---- build_notification_context (adapter) with mock ----

def test_build_notification_context_returns_dict_with_truncation(monkeypatch):
    """build_notification_context returns dict; goals_items <=5, lifestyle <=200, daily <=150."""
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

    long_lifestyle = "x" * 300
    long_daily = "y" * 200
    pack = UserContextPack(
        user_id=1,
        preferred_name="TestUser",
        language="en",
        timezone="UTC",
        quiet_hours=QuietHours(),
        goals=UserGoals(items=["a", "b", "c", "d", "e", "f"]),
        lifestyle=UserLifestyleSummary(text=long_lifestyle),
        daily_memory_summary=long_daily,
    )

    class MockService:
        def get_user_context(self, user_id):
            return pack

    def mock_get_context(db, user_id):
        return MockService().get_user_context(user_id)

    from backend.app.services.notification_runtime import user_context_adapter as adapter
    monkeypatch.setattr(adapter, "UserContextService", lambda db: MockService())

    result = build_notification_context(None, 1)
    assert result.get("preferred_name") == "TestUser"
    assert result.get("language") == "en"
    assert len(result.get("goals_items", [])) <= 5
    assert len(result.get("lifestyle_text", "")) <= 200
    assert len(result.get("daily_memory_summary", "")) <= 150


def test_build_notification_context_fail_returns_empty(monkeypatch):
    """On exception build_notification_context returns {} (fail-open)."""
    try:
        from backend.app.services.notification_runtime import user_context_adapter as adapter
    except ImportError:
        from app.services.notification_runtime import user_context_adapter as adapter

    class FailingService:
        def get_user_context(self, user_id):
            raise RuntimeError("no db")

    monkeypatch.setattr(adapter, "UserContextService", lambda db: FailingService())
    result = build_notification_context(None, 999)
    assert result == {}
