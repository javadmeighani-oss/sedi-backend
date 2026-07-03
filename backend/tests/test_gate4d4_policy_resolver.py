"""Gate 4D-4 — PolicyResolver, feature flags, and enqueue wiring tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from backend.app.models import NotificationPrefs, User, UserProfileCore
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.feature_flags import (
    gate4_policy_enforce_enabled,
    gate4_policy_log_decisions_enabled,
    gate4_policy_shadow_enabled,
)
from backend.app.services.gate4.notification_policy import NotificationPolicyDecision
from backend.app.services.gate4.policy_resolver import (
    ResolvedNotificationPolicy,
    apply_policy_to_enqueue_decision,
    evaluate_enqueue_with_gate4_policy,
    load_user_notification_policy_prefs,
    map_priority_to_risk,
    resolve_notification_policy,
)
from backend.app.services.notification_engine import NotificationBuilder


@pytest.fixture(autouse=True)
def _clear_gate4_flags(monkeypatch):
    monkeypatch.delenv("SEDI_GATE4_POLICY_SHADOW", raising=False)
    monkeypatch.delenv("SEDI_GATE4_POLICY_ENFORCE", raising=False)
    monkeypatch.delenv("SEDI_GATE4_POLICY_LOG_DECISIONS", raising=False)


def test_feature_flags_default_false():
    assert gate4_policy_shadow_enabled() is False
    assert gate4_policy_enforce_enabled() is False
    assert gate4_policy_log_decisions_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", " Yes ", "ON"])
def test_feature_flags_parse_true_values(monkeypatch, value):
    monkeypatch.setenv("SEDI_GATE4_POLICY_SHADOW", value)
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", value)
    monkeypatch.setenv("SEDI_GATE4_POLICY_LOG_DECISIONS", value)
    assert gate4_policy_shadow_enabled() is True
    assert gate4_policy_enforce_enabled() is True
    assert gate4_policy_log_decisions_enabled() is True


@pytest.mark.parametrize("value", ["", "false", "0", "no", "off", "maybe"])
def test_feature_flags_false_otherwise(monkeypatch, value):
    monkeypatch.setenv("SEDI_GATE4_POLICY_SHADOW", value)
    assert gate4_policy_shadow_enabled() is False


@pytest.fixture
def policy_user(db):
    user = User(name="Policy User", secret_key="gate4d4", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_resolver_returns_decision_with_defaults_when_prefs_missing(db, policy_user):
    decision = resolve_notification_policy(
        db,
        user_id=policy_user.id,
        risk="normal",
        category="engagement",
    )
    assert decision.should_enqueue is True
    assert decision.should_deliver_now is True
    assert decision.reason_code == "allowed"


def test_resolver_uses_notification_prefs_quiet_hours(db, policy_user):
    db.add(
        NotificationPrefs(
            user_id=policy_user.id,
            quiet_hours_enabled=True,
            quiet_start="22:00",
            quiet_end="08:00",
        )
    )
    db.commit()

    now_utc = datetime(2026, 7, 2, 20, 0, tzinfo=timezone.utc)  # 23:30 Tehran
    decision = resolve_notification_policy(
        db,
        user_id=policy_user.id,
        risk="normal",
        category="engagement",
        now_utc=now_utc,
    )
    assert decision.is_quiet_time is True
    assert decision.should_enqueue is True
    assert decision.should_deliver_now is False
    assert decision.reason_code == "quiet_or_sleep_deferred"


def test_resolver_uses_user_profile_core_timezone(db, policy_user):
    db.add(
        UserProfileCore(
            user_id=policy_user.id,
            timezone="UTC",
        )
    )
    db.add(
        NotificationPrefs(
            user_id=policy_user.id,
            quiet_hours_enabled=True,
            quiet_start="22:00",
            quiet_end="08:00",
        )
    )
    db.commit()

    now_utc = datetime(2026, 7, 2, 23, 0, tzinfo=timezone.utc)
    decision = resolve_notification_policy(
        db,
        user_id=policy_user.id,
        risk="normal",
        category="daily",
        now_utc=now_utc,
    )
    assert decision.is_quiet_time is True
    assert decision.local_time == "23:00"


def test_critical_bypasses_quiet(db, policy_user):
    db.add(
        NotificationPrefs(
            user_id=policy_user.id,
            quiet_hours_enabled=True,
            quiet_start="22:00",
            quiet_end="08:00",
        )
    )
    db.commit()

    now_utc = datetime(2026, 7, 2, 20, 0, tzinfo=timezone.utc)
    decision = resolve_notification_policy(
        db,
        user_id=policy_user.id,
        risk="critical",
        category="health_alert",
        now_utc=now_utc,
    )
    assert decision.quiet_bypass is True
    assert decision.should_deliver_now is True


def test_high_does_not_bypass_quiet(db, policy_user):
    db.add(
        NotificationPrefs(
            user_id=policy_user.id,
            quiet_hours_enabled=True,
            quiet_start="22:00",
            quiet_end="08:00",
        )
    )
    db.commit()

    now_utc = datetime(2026, 7, 2, 20, 0, tzinfo=timezone.utc)
    decision = resolve_notification_policy(
        db,
        user_id=policy_user.id,
        risk="high",
        category="health_alert",
        now_utc=now_utc,
    )
    assert decision.quiet_bypass is False
    assert decision.should_deliver_now is False


def _resolved(
    *,
    action: str = "allow",
    reason: str = "allowed",
    should_enqueue: bool = True,
    should_deliver_now: bool = True,
    reason_code: str = "allowed",
) -> ResolvedNotificationPolicy:
    decision = NotificationPolicyDecision(action=action, reason=reason, risk_level="normal")
    return ResolvedNotificationPolicy(
        decision=decision,
        should_enqueue=should_enqueue,
        should_deliver_now=should_deliver_now,
        reason_code=reason_code,
    )


def test_apply_policy_does_not_change_when_enforce_false():
    policy = _resolved(
        action="suppress",
        reason="do_not_notify",
        should_enqueue=False,
        should_deliver_now=False,
        reason_code="do_not_notify",
    )
    assert (
        apply_policy_to_enqueue_decision(True, policy, enforce_enabled=False, risk="normal")
        is True
    )


def test_apply_policy_suppresses_when_enforce_true_and_should_enqueue_false():
    policy = _resolved(
        action="suppress",
        reason="do_not_notify",
        should_enqueue=False,
        should_deliver_now=False,
        reason_code="do_not_notify",
    )
    assert (
        apply_policy_to_enqueue_decision(True, policy, enforce_enabled=True, risk="normal")
        is False
    )


def test_apply_policy_never_suppresses_critical():
    policy = _resolved(
        action="suppress",
        reason="do_not_notify",
        should_enqueue=False,
        should_deliver_now=False,
        reason_code="do_not_notify",
    )
    assert (
        apply_policy_to_enqueue_decision(True, policy, enforce_enabled=True, risk="critical")
        is True
    )


def test_fail_open_when_resolver_errors_in_integration(db, policy_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", "true")

    payload = NotificationPayload(
        user_id=policy_user.id,
        type="connection_ping",
        title="Hi",
        body="Test body",
        priority="normal",
        scheduled_for=None,
        dedupe_key=f"connection_ping:{policy_user.id}:2026-07-02:20",
        metadata={"language": "en"},
    )

    with patch(
        "backend.app.services.gate4.policy_resolver.resolve_notification_policy",
        side_effect=RuntimeError("resolver boom"),
    ):
        builder = NotificationBuilder(db)
        result = builder.persist(payload, check_dedupe=False)

    assert result is not None
    assert result.user_id == policy_user.id


def test_existing_enqueue_unchanged_when_flags_off(db, policy_user):
    payload = NotificationPayload(
        user_id=policy_user.id,
        type="connection_ping",
        title="Hi",
        body="Test body",
        priority="normal",
        scheduled_for=None,
        dedupe_key=f"connection_ping:{policy_user.id}:2026-07-02:20",
        metadata={"language": "en", "risk": "do_not_notify"},
    )
    builder = NotificationBuilder(db)
    result = builder.persist(payload, check_dedupe=False)
    assert result is not None


def test_shadow_mode_does_not_suppress_enqueue(db, policy_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_POLICY_SHADOW", "true")

    payload = NotificationPayload(
        user_id=policy_user.id,
        type="connection_ping",
        title="Hi",
        body="Test body",
        priority="normal",
        scheduled_for=None,
        dedupe_key=f"shadow:{policy_user.id}:2026-07-02:20",
        metadata={"language": "en", "risk": "do_not_notify"},
    )
    builder = NotificationBuilder(db)
    result = builder.persist(payload, check_dedupe=False)
    assert result is not None


def test_enforce_mode_suppresses_do_not_notify(db, policy_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", "true")

    payload = NotificationPayload(
        user_id=policy_user.id,
        type="connection_ping",
        title="Hi",
        body="Test body",
        priority="normal",
        scheduled_for=None,
        dedupe_key=f"enforce-dn:{policy_user.id}:2026-07-02:20",
        metadata={"language": "en", "risk": "do_not_notify"},
    )
    builder = NotificationBuilder(db)
    result = builder.persist(payload, check_dedupe=False)
    assert result is None


def test_critical_enqueue_not_suppressed_in_enforce_mode(db, policy_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_POLICY_ENFORCE", "true")

    payload = NotificationPayload(
        user_id=policy_user.id,
        type="health_alert",
        title="Alert",
        body="Critical alert body",
        priority="critical",
        scheduled_for=None,
        dedupe_key=f"enforce-critical:{policy_user.id}:2026-07-02:20",
        metadata={"language": "en"},
    )
    builder = NotificationBuilder(db)
    result = builder.persist(payload, check_dedupe=False)
    assert result is not None
    assert result.priority == "critical"


def test_load_prefs_snapshot_uses_daily_notification_time(db, policy_user):
    db.add(
        NotificationPrefs(
            user_id=policy_user.id,
            daily_notification_time="07:30",
        )
    )
    db.commit()

    prefs = load_user_notification_policy_prefs(db, policy_user.id)
    assert prefs.daily_notification_time == "07:30"


def test_evaluate_enqueue_with_gate4_policy_flags_off(db, policy_user):
    should_enqueue, decision = evaluate_enqueue_with_gate4_policy(
        db,
        user_id=policy_user.id,
        existing_should_enqueue=True,
        notification_type="connection_ping",
        priority="normal",
        metadata={"risk": "do_not_notify"},
    )
    assert should_enqueue is True
    assert decision is None


def test_map_priority_to_risk_never_maps_high_to_critical():
    assert map_priority_to_risk("high") == "high"
    assert map_priority_to_risk("critical") == "critical"
