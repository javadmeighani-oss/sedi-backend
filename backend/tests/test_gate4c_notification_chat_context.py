"""Gate 4-C — safe notification chat context builder tests."""

from __future__ import annotations

import json
from datetime import datetime

from backend.app.models import Notification
from backend.app.services.gate4.notification_chat_context import build_safe_chat_context


def _notification(**overrides):
    base = dict(
        user_id=1,
        type="companion",
        title="Hello",
        body="Check in",
        priority="normal",
        is_read=False,
        is_sent=True,
        created_at=datetime.utcnow(),
    )
    base.update(overrides)
    return Notification(**base)


def test_build_safe_chat_context_includes_safe_metadata():
    n = _notification(
        category="engagement_checkin",
        template_key="companion_ping",
        risk_level="normal",
        source_type="conversation",
        source_id="conv-1",
        context_json=json.dumps(
            {
                "action_hint": "open_chat",
                "trigger_reason": "daily_checkin",
            }
        ),
    )
    ctx = build_safe_chat_context(n)
    assert ctx["category"] == "engagement_checkin"
    assert ctx["template_key"] == "companion_ping"
    assert ctx["risk_level"] == "normal"
    assert ctx["source_type"] == "conversation"
    assert ctx["source_id"] == "conv-1"
    assert ctx["context_hints"]["action_hint"] == "open_chat"
    assert "context_json" not in ctx
    assert "notification_title" in ctx
    assert "notification_summary" not in ctx
    assert "Check in" not in json.dumps(ctx)


def test_build_safe_chat_context_strips_forbidden_keys():
    n = _notification(
        context_json=json.dumps(
            {
                "action_hint": "safe",
                "phone_number": "secret",
                "diagnosis": "bad",
                "dosage_instructions": "10mg",
                "raw_message": "private",
            }
        ),
    )
    ctx = build_safe_chat_context(n)
    hints = ctx.get("context_hints", {})
    assert hints.get("action_hint") == "safe"
    assert "phone_number" not in hints
    assert "diagnosis" not in hints
    assert "dosage_instructions" not in hints
    assert "raw_message" not in hints
    assert "context_json" not in ctx


def test_build_safe_chat_context_omits_body_with_dosage_text():
    body = "Time to take Metformin (500mg)"
    n = _notification(
        type="health_alert",
        category="medication_reminder",
        template_key="medication_reminder",
        risk_level="normal",
        title="Medication reminder",
        body=body,
        context_json=json.dumps({"action_hint": "open_chat", "trigger_reason": "scheduled_dose"}),
    )
    ctx = build_safe_chat_context(n)
    serialized = json.dumps(ctx)
    assert "500mg" not in serialized
    assert "Metformin" not in serialized
    assert body not in serialized
    assert "notification_summary" not in ctx
    assert ctx["category"] == "medication_reminder"
    assert ctx["template_key"] == "medication_reminder"
    assert ctx["risk_level"] == "normal"
    assert ctx["context_hints"]["action_hint"] == "open_chat"


def test_build_safe_chat_context_truncates_long_title():
    long_title = "T" * 500
    long_body = "B" * 500
    n = _notification(title=long_title, body=long_body)
    ctx = build_safe_chat_context(n)
    assert len(ctx["notification_title"]) <= 200
    assert "notification_summary" not in ctx
    assert "B" * 10 not in json.dumps(ctx)


def test_build_safe_chat_context_resolves_effective_category_and_risk():
    n = _notification(type="morning_brief", priority="high", category=None, risk_level=None)
    ctx = build_safe_chat_context(n)
    assert ctx["category"] == "daily_status"
    assert ctx["risk_level"] == "high"
