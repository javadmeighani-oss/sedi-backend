"""Gate 4D-1 — pure notification policy tests (no DB, no network)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from backend.app.services.gate4.notification_policy import (
    GATE4D_POLICY_VERSION,
    NotificationPolicyDecision,
    evaluate_notification_policy,
)


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_default_policy_allows():
    decision = evaluate_notification_policy(
        category="engagement_checkin",
        channel="push",
        risk_level="normal",
    )
    assert decision.action == "allow"
    assert decision.reason == "allowed"
    assert decision.risk_level == "normal"


def test_disabled_non_critical_channel_suppresses():
    decision = evaluate_notification_policy(
        category="engagement_checkin",
        channel="companion",
        risk_level="normal",
        user_channel_enabled=False,
    )
    assert decision.action == "suppress"
    assert decision.reason == "user_preference_disabled"


def test_disabled_category_suppresses_non_critical():
    decision = evaluate_notification_policy(
        category="engagement_checkin",
        channel="push",
        risk_level="low",
        user_category_enabled=False,
    )
    assert decision.action == "suppress"
    assert decision.reason == "user_preference_disabled"


def test_disabled_channel_still_allows_critical():
    decision = evaluate_notification_policy(
        category="critical_alert",
        channel="health_alert",
        risk_level="critical",
        user_channel_enabled=False,
        user_category_enabled=False,
        feedback_suppressed=True,
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
        active_conversation=True,
    )
    assert decision.action == "allow"
    assert decision.reason == "critical_allowed"


def test_quiet_hours_defer_normal_risk():
    decision = evaluate_notification_policy(
        category="daily_status",
        channel="push",
        risk_level="normal",
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
        now=_utc(2026, 7, 2, 23, 0),
    )
    assert decision.action == "defer"
    assert decision.reason == "quiet_hours"
    assert decision.defer_until is not None


def test_quiet_hours_allow_critical():
    decision = evaluate_notification_policy(
        category="critical_alert",
        channel="push",
        risk_level="critical",
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
    )
    assert decision.action == "allow"
    assert decision.reason == "critical_allowed"


@pytest.mark.parametrize("risk", ["high", "normal", "low"])
def test_high_and_non_critical_do_not_bypass_quiet_hours(risk: str):
    decision = evaluate_notification_policy(
        category="health_alert",
        channel="push",
        risk_level=risk,
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
    )
    assert decision.action == "defer"
    assert decision.reason == "quiet_hours"


def test_priority_maps_to_risk_when_risk_level_missing():
    decision = evaluate_notification_policy(
        category="health_alert",
        channel="push",
        priority="high",
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
    )
    assert decision.risk_level == "high"
    assert decision.action == "defer"


def test_feedback_suppression_suppresses_low_risk():
    decision = evaluate_notification_policy(
        category="engagement_checkin",
        channel="push",
        risk_level="low",
        feedback_suppressed=True,
    )
    assert decision.action == "suppress"
    assert decision.reason == "feedback_suppressed"


def test_feedback_suppression_does_not_suppress_critical():
    decision = evaluate_notification_policy(
        category="critical_alert",
        channel="push",
        risk_level="critical",
        feedback_suppressed=True,
    )
    assert decision.action == "allow"
    assert decision.reason == "critical_allowed"


def test_active_conversation_defers_low_risk_nudge():
    decision = evaluate_notification_policy(
        category="engagement_checkin",
        channel="companion",
        risk_level="normal",
        active_conversation=True,
        now=_utc(2026, 7, 2, 12, 0),
    )
    assert decision.action == "defer"
    assert decision.reason == "active_conversation"
    assert decision.defer_until is not None


def test_active_conversation_does_not_suppress_critical():
    decision = evaluate_notification_policy(
        category="critical_alert",
        channel="push",
        risk_level="critical",
        active_conversation=True,
    )
    assert decision.action == "allow"
    assert decision.reason == "critical_allowed"


def test_unknown_risk_fails_open_to_allow():
    decision = evaluate_notification_policy(
        category="unknown_category",
        channel="push",
        risk_level="not_a_real_risk",
    )
    assert decision.action == "allow"
    assert decision.reason == "allowed"
    assert decision.risk_level == "not_a_real_risk"


def test_unknown_category_and_missing_risk_fail_open():
    decision = evaluate_notification_policy(
        category=None,
        channel=None,
        priority=None,
        risk_level=None,
    )
    assert decision.action == "allow"
    assert decision.risk_level == "normal"


def test_do_not_notify_suppresses():
    decision = evaluate_notification_policy(
        category="system",
        channel="push",
        risk_level="do_not_notify",
    )
    assert decision.action == "suppress"
    assert decision.reason == "do_not_notify"


def test_feedback_suppression_takes_precedence_over_quiet_hours():
    decision = evaluate_notification_policy(
        category="engagement_checkin",
        channel="push",
        risk_level="normal",
        feedback_suppressed=True,
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
    )
    assert decision.action == "suppress"
    assert decision.reason == "feedback_suppressed"


def test_quiet_hours_take_precedence_over_active_conversation():
    decision = evaluate_notification_policy(
        category="engagement_checkin",
        channel="push",
        risk_level="normal",
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
        active_conversation=True,
    )
    assert decision.action == "defer"
    assert decision.reason == "quiet_hours"


def test_policy_decision_is_serializable_and_stable():
    decision = evaluate_notification_policy(
        category="daily_status",
        channel="push",
        risk_level="normal",
        active_conversation=True,
        now=_utc(2026, 7, 2, 12, 0),
    )
    payload = decision.to_dict()
    assert payload["action"] == "defer"
    assert payload["reason"] == "active_conversation"
    assert payload["policy_version"] == GATE4D_POLICY_VERSION
    assert payload["category"] == "daily_status"
    assert payload["channel"] == "push"
    assert payload["risk_level"] == "normal"
    assert "defer_until" in payload
    # Round-trip via JSON must not raise and must preserve action/reason
    restored = json.loads(json.dumps(payload, sort_keys=True))
    assert restored["action"] == "defer"
    assert restored["reason"] == "active_conversation"
    forbidden = (
        "dosage",
        "diagnosis",
        "medication_change",
        "raw_message",
        "user_message",
        "phone",
        "token",
    )
    blob = json.dumps(payload).lower()
    for term in forbidden:
        assert term not in blob


def test_decision_dataclass_frozen():
    decision = NotificationPolicyDecision(action="allow", reason="allowed")
    with pytest.raises(Exception):
        decision.action = "suppress"  # type: ignore[misc]
