"""Gate 4D-6 — feedback suppress/defer and active conversation tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models import InteractionEvent, Notification, NotificationGuardState, User
from backend.app.services.gate4.feature_flags import (
    gate4_active_conversation_defer_enabled,
    gate4_feedback_policy_enabled,
)
from backend.app.services.gate4.feedback_policy import (
    ACTIVE_CONVERSATION_WINDOW_MINUTES,
    apply_feedback_policy,
    augment_policy_decision_with_gate4d6,
    build_feedback_rule_id,
    get_feedback_policy_block,
    is_user_active_conversation,
)
from backend.app.services.gate4.notification_contract import (
    NOT_NOW_SUPPRESS_HOURS,
    TALK_LATER_DEFER_HOURS,
    SmartNotificationAction,
)
from backend.app.services.gate4.notification_policy import (
    NotificationPolicyDecision,
    evaluate_notification_policy,
)
from backend.app.services.gate4.policy_resolver import (
    resolve_notification_policy,
    should_deliver_now,
    should_enqueue,
)


@pytest.fixture(autouse=True)
def _clear_gate4d6_flags(monkeypatch):
    monkeypatch.delenv("SEDI_GATE4_FEEDBACK_POLICY", raising=False)
    monkeypatch.delenv("SEDI_GATE4_ACTIVE_CONVERSATION_DEFER", raising=False)


def test_feature_flags_default_false():
    assert gate4_feedback_policy_enabled() is False
    assert gate4_active_conversation_defer_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE"])
def test_feedback_policy_flag_parses_true(monkeypatch, value):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", value)
    assert gate4_feedback_policy_enabled() is True


@pytest.mark.parametrize("value", ["1", "true", "yes", "on"])
def test_active_conversation_flag_parses_true(monkeypatch, value):
    monkeypatch.setenv("SEDI_GATE4_ACTIVE_CONVERSATION_DEFER", value)
    assert gate4_active_conversation_defer_enabled() is True


@pytest.fixture
def fb_user(db):
    user = User(name="Feedback User", secret_key="d6", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def sample_notification(db, fb_user):
    notif = Notification(
        user_id=fb_user.id,
        type="connection_ping",
        title="Hi",
        body="Body",
        priority="normal",
        channel="engagement",
        dedupe_key="d6:sample:1",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def _allowed_decision() -> NotificationPolicyDecision:
    return NotificationPolicyDecision(action="allow", reason="allowed", risk_level="normal")


def test_not_now_creates_24h_suppress_state(db, fb_user, sample_notification, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)

    result = apply_feedback_policy(
        db,
        user_id=fb_user.id,
        notification=sample_notification,
        canonical_action=SmartNotificationAction.NOT_NOW.value,
        now_utc=now,
    )
    db.commit()

    assert result["guard_updated"] is True
    rule_id = build_feedback_rule_id("not_now", "engagement", "engagement")
    row = (
        db.query(NotificationGuardState)
        .filter(
            NotificationGuardState.user_id == fb_user.id,
            NotificationGuardState.rule_id == rule_id,
        )
        .one()
    )
    assert row.cooldown_until is not None
    delta = row.cooldown_until - datetime(2026, 7, 2, 12, 0)
    assert delta.total_seconds() == pytest.approx(NOT_NOW_SUPPRESS_HOURS * 3600, rel=1)


def test_talk_later_creates_4h_defer_state(db, fb_user, sample_notification, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)

    apply_feedback_policy(
        db,
        user_id=fb_user.id,
        notification=sample_notification,
        canonical_action=SmartNotificationAction.TALK_LATER.value,
        now_utc=now,
    )
    db.commit()

    rule_id = build_feedback_rule_id("talk_later", "engagement", "engagement")
    row = (
        db.query(NotificationGuardState)
        .filter(
            NotificationGuardState.user_id == fb_user.id,
            NotificationGuardState.rule_id == rule_id,
        )
        .one()
    )
    delta = row.cooldown_until - datetime(2026, 7, 2, 12, 0)
    assert delta.total_seconds() == pytest.approx(TALK_LATER_DEFER_HOURS * 3600, rel=1)


def test_ack_thanks_does_not_block_future(db, fb_user, sample_notification, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    apply_feedback_policy(
        db,
        user_id=fb_user.id,
        notification=sample_notification,
        canonical_action=SmartNotificationAction.ACK_THANKS.value,
    )
    db.commit()

    block = get_feedback_policy_block(
        db, user_id=fb_user.id, channel="engagement", category="engagement"
    )
    assert block["blocked"] is False


def test_open_chat_does_not_create_suppress_guard(db, fb_user, sample_notification, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    result = apply_feedback_policy(
        db,
        user_id=fb_user.id,
        notification=sample_notification,
        canonical_action=SmartNotificationAction.OPEN_CHAT.value,
    )
    db.commit()
    assert result["guard_updated"] is False
    assert (
        db.query(NotificationGuardState)
        .filter(NotificationGuardState.user_id == fb_user.id)
        .count()
        == 0
    )


def test_legacy_dismiss_maps_to_not_now_via_endpoint(db, fb_user, sample_notification, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    from backend.app.routers.notifications import submit_notification_feedback

    result = submit_notification_feedback(
        notification_id=sample_notification.id,
        payload={"reaction": "dismiss"},
        auth_user=fb_user,
        user_id=None,
        db=db,
    )
    assert result.ok is True
    assert "gate4_feedback_policy" in result.data
    rule_id = build_feedback_rule_id("not_now", "engagement", "engagement")
    row = (
        db.query(NotificationGuardState)
        .filter(NotificationGuardState.user_id == fb_user.id, NotificationGuardState.rule_id == rule_id)
        .one_or_none()
    )
    assert row is not None


def test_legacy_open_chat_normalizes(db, fb_user, sample_notification, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    from backend.app.routers.notifications import submit_notification_feedback

    result = submit_notification_feedback(
        notification_id=sample_notification.id,
        payload={"reaction": "interact", "action_id": "open_chat"},
        auth_user=fb_user,
        user_id=None,
        db=db,
    )
    assert result.ok is True
    event = (
        db.query(InteractionEvent)
        .filter(InteractionEvent.user_id == fb_user.id)
        .order_by(InteractionEvent.id.desc())
        .first()
    )
    assert event is not None
    assert event.event_type == "notification_open_chat"


def test_critical_ignores_feedback_suppress(db, fb_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    channel = "health_alert"
    scope = "health_alert"
    db.add(
        NotificationGuardState(
            user_id=fb_user.id,
            channel=channel,
            rule_id=build_feedback_rule_id("not_now", channel, scope),
            last_sent_at=datetime(2026, 7, 2, 12, 0),
            cooldown_until=datetime(2026, 7, 3, 12, 0),
        )
    )
    db.commit()

    decision = augment_policy_decision_with_gate4d6(
        db,
        user_id=fb_user.id,
        risk="critical",
        category=scope,
        channel=channel,
        decision=_allowed_decision(),
        now_utc=now,
    )
    assert should_enqueue(decision) is True
    assert should_deliver_now(decision) is True


def test_non_critical_respects_suppress(db, fb_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    channel = "engagement"
    scope = "engagement"
    db.add(
        NotificationGuardState(
            user_id=fb_user.id,
            channel=channel,
            rule_id=build_feedback_rule_id("not_now", channel, scope),
            last_sent_at=datetime(2026, 7, 2, 12, 0),
            cooldown_until=datetime(2026, 7, 3, 12, 0),
        )
    )
    db.commit()

    decision = augment_policy_decision_with_gate4d6(
        db,
        user_id=fb_user.id,
        risk="normal",
        category=scope,
        channel=channel,
        decision=_allowed_decision(),
        now_utc=now,
    )
    assert decision.action == "suppress"
    assert decision.reason == "feedback_suppressed"


def test_non_critical_respects_defer_with_next_allowed(db, fb_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_FEEDBACK_POLICY", "true")
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    until = datetime(2026, 7, 2, 16, 0)
    channel = "engagement"
    scope = "engagement"
    db.add(
        NotificationGuardState(
            user_id=fb_user.id,
            channel=channel,
            rule_id=build_feedback_rule_id("talk_later", channel, scope),
            last_sent_at=datetime(2026, 7, 2, 12, 0),
            cooldown_until=until,
        )
    )
    db.commit()

    decision = augment_policy_decision_with_gate4d6(
        db,
        user_id=fb_user.id,
        risk="normal",
        category=scope,
        channel=channel,
        decision=_allowed_decision(),
        now_utc=now,
    )
    assert decision.action == "defer"
    assert decision.reason == "feedback_deferred"
    assert decision.defer_until is not None


def test_feedback_endpoint_backward_compatible_when_flag_off(db, fb_user, sample_notification):
    from backend.app.routers.notifications import submit_notification_feedback

    result = submit_notification_feedback(
        notification_id=sample_notification.id,
        payload={"reaction": "like"},
        auth_user=fb_user,
        user_id=None,
        db=db,
    )
    assert result.ok is True
    assert result.data["feedback_received"] is True
    assert "gate4_feedback_policy" not in result.data
    assert db.query(NotificationGuardState).filter(NotificationGuardState.user_id == fb_user.id).count() == 0


def test_active_conversation_within_15_minutes(db, fb_user):
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    db.add(
        InteractionEvent(
            user_id=fb_user.id,
            event_type="chat_message",
            source="chat",
            created_at=datetime(2026, 7, 2, 11, 50),
        )
    )
    db.commit()
    assert is_user_active_conversation(db, user_id=fb_user.id, now_utc=now) is True


def test_active_conversation_outside_window(db, fb_user):
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    db.add(
        InteractionEvent(
            user_id=fb_user.id,
            event_type="notification_open_chat",
            source="notification",
            created_at=datetime(2026, 7, 2, 11, 30),
        )
    )
    db.commit()
    assert is_user_active_conversation(db, user_id=fb_user.id, now_utc=now) is False


def test_active_conversation_does_not_affect_critical(db, fb_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_ACTIVE_CONVERSATION_DEFER", "true")
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    db.add(
        InteractionEvent(
            user_id=fb_user.id,
            event_type="chat_message",
            source="chat",
            created_at=datetime(2026, 7, 2, 11, 55),
        )
    )
    db.commit()

    decision = augment_policy_decision_with_gate4d6(
        db,
        user_id=fb_user.id,
        risk="critical",
        category="health_alert",
        channel="health_alert",
        decision=_allowed_decision(),
        now_utc=now,
    )
    assert should_deliver_now(decision) is True


def test_active_conversation_defers_non_critical(db, fb_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_ACTIVE_CONVERSATION_DEFER", "true")
    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)
    db.add(
        InteractionEvent(
            user_id=fb_user.id,
            event_type="chat_message",
            source="chat",
            created_at=datetime(2026, 7, 2, 11, 55),
        )
    )
    db.commit()

    decision = augment_policy_decision_with_gate4d6(
        db,
        user_id=fb_user.id,
        risk="normal",
        category="engagement",
        channel="engagement",
        decision=_allowed_decision(),
        now_utc=now,
    )
    assert decision.action == "defer"
    assert decision.reason == "active_conversation"


def test_apply_feedback_no_op_when_flag_off(db, fb_user, sample_notification):
    result = apply_feedback_policy(
        db,
        user_id=fb_user.id,
        notification=sample_notification,
        canonical_action=SmartNotificationAction.NOT_NOW.value,
    )
    assert result["applied"] is False
    assert db.query(NotificationGuardState).count() == 0


def test_resolve_policy_unchanged_when_flags_off(db, fb_user):
    decision = resolve_notification_policy(
        db,
        user_id=fb_user.id,
        risk="normal",
        category="engagement",
        now_utc=datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
    )
    assert decision.reason_code == "allowed"


def test_active_conversation_window_constant():
    assert ACTIVE_CONVERSATION_WINDOW_MINUTES == 15
