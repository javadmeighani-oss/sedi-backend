"""Gate 4D-2 — policy resolver and feature flags (no DB, no network)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.app.services.gate4.feature_flags import (
    gate4_policy_active,
    gate4_policy_enforce_enabled,
    gate4_policy_log_decisions_enabled,
    gate4_policy_shadow_enabled,
)
from backend.app.services.gate4.notification_policy import NotificationPolicyDecision
from backend.app.services.gate4.policy_resolver import (
    PolicyResolverInput,
    build_resolver_input_from_notification_like,
    resolve_notification_policy_from_input,
    safe_resolve_notification_policy_from_input,
    should_deliver_now,
    should_enqueue,
)

_PII_LIKE_KEYS = frozenset(
    {
        "body",
        "title",
        "phone",
        "token",
        "password",
        "secret",
        "diagnosis",
        "dosage",
        "user_message",
        "raw_message",
    }
)


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clear_gate4_policy_flags(monkeypatch):
    monkeypatch.delenv("SEDI_GATE4_POLICY_SHADOW", raising=False)
    monkeypatch.delenv("SEDI_GATE4_POLICY_ENFORCE", raising=False)
    monkeypatch.delenv("SEDI_GATE4_POLICY_LOG_DECISIONS", raising=False)


def test_feature_flags_default_off():
    assert gate4_policy_shadow_enabled() is False
    assert gate4_policy_enforce_enabled() is False
    assert gate4_policy_log_decisions_enabled() is False
    assert gate4_policy_active() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", " Yes ", "ON"])
def test_feature_flags_parse_true_values(monkeypatch, value):
    monkeypatch.setenv("SEDI_GATE4_POLICY_SHADOW", value)
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", value)
    monkeypatch.setenv("SEDI_GATE4_POLICY_LOG_DECISIONS", value)
    assert gate4_policy_shadow_enabled() is True
    assert gate4_policy_enforce_enabled() is True
    assert gate4_policy_log_decisions_enabled() is True
    assert gate4_policy_active() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "maybe", "unknown"])
def test_feature_flags_false_otherwise(monkeypatch, value):
    monkeypatch.setenv("SEDI_GATE4_POLICY_SHADOW", value)
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", value)
    monkeypatch.setenv("SEDI_GATE4_POLICY_LOG_DECISIONS", value)
    assert gate4_policy_shadow_enabled() is False
    assert gate4_policy_enforce_enabled() is False
    assert gate4_policy_log_decisions_enabled() is False
    assert gate4_policy_active() is False


def test_gate4_policy_active_when_shadow_only(monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_POLICY_SHADOW", "true")
    assert gate4_policy_active() is True


def test_gate4_policy_active_when_enforce_only(monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", "true")
    assert gate4_policy_active() is True


def test_explicit_normal_resolver_input_allows():
    resolver_input = PolicyResolverInput(
        category="engagement_checkin",
        channel="push",
        risk_level="normal",
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    assert decision.action == "allow"
    assert decision.reason == "allowed"


def test_critical_bypass_under_quiet_and_disabled_prefs():
    resolver_input = PolicyResolverInput(
        category="critical_alert",
        channel="health_alert",
        risk_level="critical",
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
        user_channel_enabled=False,
        user_category_enabled=False,
        feedback_suppressed=True,
        active_conversation=True,
        now=_utc(2026, 7, 2, 23, 0),
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    assert decision.action == "allow"
    assert decision.reason == "critical_allowed"


def test_quiet_hours_defer_non_critical():
    resolver_input = PolicyResolverInput(
        category="engagement_checkin",
        channel="push",
        risk_level="normal",
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
        now=_utc(2026, 7, 2, 23, 0),
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    assert decision.action == "defer"
    assert decision.reason == "quiet_hours"
    assert decision.defer_until is not None


def test_high_risk_does_not_bypass_quiet_hours():
    resolver_input = PolicyResolverInput(
        category="health_status",
        channel="push",
        risk_level="high",
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
        now=_utc(2026, 7, 2, 23, 0),
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    assert decision.action == "defer"
    assert decision.reason == "quiet_hours"


def test_disabled_channel_suppresses_non_critical():
    resolver_input = PolicyResolverInput(
        category="engagement_checkin",
        channel="companion",
        risk_level="normal",
        user_channel_enabled=False,
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    assert decision.action == "suppress"
    assert decision.reason == "user_preference_disabled"


def test_disabled_category_suppresses_non_critical():
    resolver_input = PolicyResolverInput(
        category="engagement_checkin",
        channel="push",
        risk_level="low",
        user_category_enabled=False,
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    assert decision.action == "suppress"
    assert decision.reason == "user_preference_disabled"


def test_unknown_priority_fails_open_to_normal_allow():
    resolver_input = PolicyResolverInput(
        category="engagement_checkin",
        channel="push",
        priority="totally_unknown",
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    assert decision.action == "allow"
    assert decision.risk_level == "normal"


def test_unknown_risk_fails_open_safely():
    resolver_input = PolicyResolverInput(
        category="engagement_checkin",
        channel="push",
        risk_level="mystery_risk",
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    assert decision.action in {"allow", "defer", "suppress"}
    assert decision.risk_level == "mystery_risk"


def test_safe_resolver_fail_open_on_forced_exception():
    resolver_input = PolicyResolverInput(
        category="engagement_checkin",
        channel="push",
        risk_level="normal",
    )
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_notification_policy",
        side_effect=RuntimeError("boom"),
    ):
        decision = safe_resolve_notification_policy_from_input(resolver_input)
    assert decision.action == "allow"
    assert decision.reason == "resolver_fail_open"


def test_decision_to_dict_is_json_safe():
    resolver_input = PolicyResolverInput(
        category="engagement_checkin",
        channel="push",
        risk_level="normal",
        quiet_hours_enabled=True,
        is_quiet_hours_now=True,
        now=_utc(2026, 7, 2, 23, 0),
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    payload = decision.to_dict()
    json.dumps(payload)
    assert payload["action"] == "defer"
    assert "defer_until" in payload


def test_no_pii_like_keys_in_resolver_output():
    resolver_input = build_resolver_input_from_notification_like(
        notification_type="connection_ping",
        priority="normal",
        channel="push",
        metadata={
            "title": "secret title",
            "body": "secret body",
            "phone": "555-0000",
            "category": "engagement_checkin",
        },
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    keys = set(decision.to_dict().keys())
    assert keys.isdisjoint(_PII_LIKE_KEYS)


@pytest.mark.parametrize(
    ("action", "expected_enqueue", "expected_deliver"),
    [
        ("allow", True, True),
        ("defer", True, False),
        ("suppress", False, False),
    ],
)
def test_should_enqueue_and_deliver_match_action(action, expected_enqueue, expected_deliver):
    decision = NotificationPolicyDecision(
        action=action,
        reason="test",
        risk_level="normal",
        category="engagement_checkin",
        channel="push",
    )
    assert should_enqueue(decision) is expected_enqueue
    assert should_deliver_now(decision) is expected_deliver


def test_build_resolver_input_uses_notification_context_mappers():
    resolver_input = build_resolver_input_from_notification_like(
        notification_type="morning_brief",
        priority="high",
    )
    assert resolver_input.category == "daily_status"
    assert resolver_input.risk_level == "high"
    assert resolver_input.channel == "push"
