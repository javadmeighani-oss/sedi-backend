"""I10 provider-delivery freshness authority (B4-A4). No real FCM/network."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_contract import (
    ACTION_LABELS,
    SmartNotificationAction,
    get_action_label,
    normalize_language,
)
from backend.app.services.gate4.policy_prefs_bridge import get_local_now
from backend.app.services.gate4.scheduler_timing import (
    GATE4_DAILY_TOLERANCE_MINUTES,
    resolve_user_daily_notification_time_for_scheduler,
    resolve_user_timezone_for_scheduler,
)
from backend.app.services.i10.canonical_policy import evaluate_i10_canonical_policy
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification, evaluate_foundation_policy
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
from backend.app.services.i10.provider_delivery_policy import (
    CONTEXTUAL_TTL_HOURS,
    ENGAGEMENT_NUDGE_TTL_HOURS,
    PRESENCE_REENGAGEMENT_TTL_HOURS,
    ProviderFreshnessOutcome,
    apply_i10_provider_lifetime,
    compute_effective_fcm_ttl,
    evaluate_notification_provider_freshness,
    evaluate_provider_freshness,
)
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.notifications.delivery_service import (
    DeliveryService,
    FCMAdapter,
    is_real_fcm_adapter,
    provider_delivery_enabled,
)
from backend.app.services.notification_runtime.templates_v1 import TEMPLATES_V1

_GATE = "SEDI_NOTIFICATION_PROVIDER_DELIVERY_ENABLED"
_CANONICAL_ACTIONS = (
    SmartNotificationAction.ACK_THANKS.value,
    SmartNotificationAction.NOT_NOW.value,
    SmartNotificationAction.TALK_LATER.value,
    SmartNotificationAction.OPEN_CHAT.value,
)


class RecordingFCMAdapter:
    channel = "fcm"

    def __init__(self):
        self.calls = 0
        self.notifications = []

    def send(self, notification):
        self.calls += 1
        self.notifications.append(notification)
        notification.provider = self.channel
        notification.is_sent = True
        notification.status = "sent"
        notification.sent_at = datetime.utcnow()
        notification.last_error = None
        return True


def _android_token(db, user: models.User) -> models.PushDevice:
    row = models.PushDevice(
        user_id=user.id,
        platform="android",
        fcm_token=("fcm-auth-" + uuid4().hex + "x" * 80)[:96],
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _deliver_via_fcm_adapter(db, monkeypatch):
    captured: list[dict] = []

    def _fake_send(**kwargs):
        captured.append(kwargs)
        tokens = kwargs.get("tokens") or ["tok"]
        return (1, [(tokens[0], "mock", None)])

    monkeypatch.setenv(_GATE, "true")
    with patch(
        "backend.app.services.notifications.fcm_client.send_push_to_tokens",
        side_effect=_fake_send,
    ):
        sent = DeliveryService(db=db, adapter=FCMAdapter(db=db, timeout_sec=1)).deliver_pending(
            limit=10
        )
    return sent, captured


def _user(db, name: str, *, tz: str | None = None, lang: str = "en") -> models.User:
    user = models.User(name=name, secret_key=f"sk-{name}-{uuid4().hex[:8]}", preferred_language=lang)
    db.add(user)
    db.commit()
    db.refresh(user)
    if tz:
        db.add(models.UserProfileCore(user_id=user.id, timezone=tz))
        db.commit()
    return user


def _candidate(
    *,
    subject_id: int,
    recipient_id: int,
    family: I10SemanticFamily,
    key: str | None = None,
    expires_at=None,
    valid_from=None,
) -> I10NotificationCandidate:
    return I10NotificationCandidate(
        candidate_key=key or f"fresh-{family.value}-{uuid4().hex[:10]}",
        health_subject_id=subject_id,
        recipient_user_id=recipient_id,
        notification_scope=I10NotificationScope.GENERAL_STATUS,
        source_owner="I10_TEST",
        source_type="provider_freshness",
        source_id="1",
        semantic_family=family,
        privacy_hint=I10PrivacyClass.PRIVATE,
        expires_at=expires_at,
        valid_from=valid_from,
    )


def _decision(
    db,
    user: models.User,
    *,
    family: str,
    expires_at=None,
    created_at=None,
    decision: str = "SEND",
    subject_id: int | None = None,
) -> models.I10NotificationDecision:
    row = models.I10NotificationDecision(
        candidate_key=f"dec-{family}-{uuid4().hex[:10]}",
        health_subject_id=subject_id,
        recipient_user_id=user.id,
        source_owner="I10_TEST",
        source_type="provider_freshness",
        source_id="1",
        semantic_family=family,
        decision=decision,
        reason_code="POLICY_ALLOW",
        expires_at=expires_at,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _queued(
    db,
    user: models.User,
    *,
    decision: models.I10NotificationDecision | None = None,
    family: str | None = None,
    priority: str = "normal",
    risk_level: str | None = None,
    ttl_seconds: int | None = 3600,
    status: str = "queued",
) -> models.Notification:
    notif = models.Notification(
        user_id=user.id,
        type="connection_ping",
        title="T",
        body="B",
        priority=priority,
        risk_level=risk_level,
        is_read=False,
        is_sent=False,
        status=status,
        sent_at=None,
        ttl_seconds=ttl_seconds,
        semantic_family=family or (decision.semantic_family if decision else None),
        i10_policy_decision_id=decision.id if decision else None,
        created_at=datetime.utcnow(),
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    if decision is not None:
        decision.notification_id = notif.id
        db.add(decision)
        db.commit()
    return notif


def test_a_presence_reengagement_default_is_4h(db):
    user = _user(db, "ttl-presence")
    now = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    cand = _candidate(subject_id=1, recipient_id=user.id, family=I10SemanticFamily.PRESENCE_REENGAGEMENT)
    stamped = apply_i10_provider_lifetime(db, cand, now_utc=now)
    assert stamped.expires_at == now + timedelta(hours=PRESENCE_REENGAGEMENT_TTL_HOURS)
    assert PRESENCE_REENGAGEMENT_TTL_HOURS == 4


def test_a_engagement_nudge_default_is_3h(db):
    user = _user(db, "ttl-nudge")
    now = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    cand = _candidate(subject_id=1, recipient_id=user.id, family=I10SemanticFamily.ENGAGEMENT_NUDGE)
    stamped = apply_i10_provider_lifetime(db, cand, now_utc=now)
    assert stamped.expires_at == now + timedelta(hours=ENGAGEMENT_NUDGE_TTL_HOURS)
    assert ENGAGEMENT_NUDGE_TTL_HOURS == 3


@pytest.mark.parametrize(
    "family",
    [
        I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP,
        I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING,
        I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP,
        I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP,
    ],
)
def test_a_contextual_coaching_default_is_24h(db, family):
    user = _user(db, f"ttl-{family.value}")
    now = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    cand = _candidate(subject_id=1, recipient_id=user.id, family=family)
    stamped = apply_i10_provider_lifetime(db, cand, now_utc=now)
    assert stamped.expires_at == now + timedelta(hours=CONTEXTUAL_TTL_HOURS)
    assert CONTEXTUAL_TTL_HOURS == 24


def test_a_explicit_upstream_expires_at_preserved_exactly(db):
    user = _user(db, "ttl-preserve")
    now = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    explicit = datetime(2026, 9, 25, 11, 15, 30, 123000, tzinfo=timezone.utc)
    cand = _candidate(
        subject_id=1,
        recipient_id=user.id,
        family=I10SemanticFamily.PRESENCE_REENGAGEMENT,
        expires_at=explicit,
    )
    stamped = apply_i10_provider_lifetime(db, cand, now_utc=now)
    assert stamped.expires_at is explicit
    assert stamped.expires_at == explicit


def test_a_enqueue_stamps_decision_expires_at(db):
    user = _user(db, "ttl-enqueue")
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    reference_now = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    cand = _candidate(
        subject_id=subject.id,
        recipient_id=user.id,
        family=I10SemanticFamily.PRESENCE_REENGAGEMENT,
    )
    payload = NotificationPayload(
        user_id=user.id,
        type="connection_ping",
        title="T",
        body="B",
        priority="normal",
        dedupe_key=f"fresh-enq-{uuid4().hex}",
        health_subject_id=subject.id,
        semantic_family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value,
    )

    def _foundation_at_reference(*, candidate, authorized):
        if not authorized:
            return evaluate_foundation_policy(candidate=candidate, authorized=authorized)
        if candidate.expires_at is not None and candidate.expires_at <= reference_now:
            return I10DecisionValue.EXPIRE, "CANDIDATE_EXPIRED"
        return I10DecisionValue.SEND, "FOUNDATION_SEND"

    with patch(
        "backend.app.services.i10.intake.apply_i10_provider_lifetime",
        side_effect=lambda db, candidate, now_utc=None: apply_i10_provider_lifetime(
            db, candidate, now_utc=reference_now
        ),
    ), patch(
        "backend.app.services.i10.intake.evaluate_foundation_policy",
        side_effect=_foundation_at_reference,
    ), patch(
        "backend.app.services.i10.intake.evaluate_i10_canonical_policy",
        side_effect=lambda db, **kwargs: evaluate_i10_canonical_policy(
            db, **{**kwargs, "now_utc": reference_now}
        ),
    ):
        result = enqueue_i10_notification(db, candidate=cand, payload=payload)
    assert result.decision.value == "SEND"
    row = db.query(models.I10NotificationDecision).filter_by(id=result.decision_id).one()
    assert row.expires_at is not None
    persisted = row.expires_at
    if persisted.tzinfo is None:
        persisted = persisted.replace(tzinfo=timezone.utc)
    else:
        persisted = persisted.astimezone(timezone.utc)
    assert persisted == reference_now + timedelta(hours=PRESENCE_REENGAGEMENT_TTL_HOURS)
    assert PRESENCE_REENGAGEMENT_TTL_HOURS == 4
    assert row.decision == "SEND"


def test_b_morning_reuses_canonical_scheduler_window(db):
    user = _user(db, "morning-win", tz="Asia/Tehran")
    db.add(models.NotificationPrefs(user_id=user.id, daily_notification_time="08:00"))
    db.commit()
    now = datetime(2026, 9, 25, 4, 30, tzinfo=timezone.utc)  # 08:00 Asia/Tehran
    cand = _candidate(subject_id=1, recipient_id=user.id, family=I10SemanticFamily.MORNING_CHECK_IN)
    stamped = apply_i10_provider_lifetime(db, cand, now_utc=now)
    daily = resolve_user_daily_notification_time_for_scheduler(db, user)
    tz_name = resolve_user_timezone_for_scheduler(db, user)
    assert daily == "08:00"
    assert tz_name == "Asia/Tehran"
    assert GATE4_DAILY_TOLERANCE_MINUTES == 10
    assert stamped.expires_at is not None
    local_end = stamped.expires_at.astimezone(timezone.utc)
    # 08:10 Tehran = 04:40 UTC
    assert local_end == datetime(2026, 9, 25, 4, 40, tzinfo=timezone.utc)


def test_b_morning_past_window_stamps_expiry_and_intake_expires(db):
    user = _user(db, "morning-past", tz="Asia/Tehran")
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    db.add(models.NotificationPrefs(user_id=user.id, daily_notification_time="08:00"))
    db.commit()
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)  # after 08:10 Tehran
    cand = _candidate(
        subject_id=subject.id,
        recipient_id=user.id,
        family=I10SemanticFamily.MORNING_CHECK_IN,
    )
    stamped = apply_i10_provider_lifetime(db, cand, now_utc=now)
    assert stamped.expires_at is not None
    assert stamped.expires_at <= now
    payload = NotificationPayload(
        user_id=user.id,
        type="morning_brief",
        title="T",
        body="B",
        priority="normal",
        dedupe_key=f"morning-past-{uuid4().hex}",
        health_subject_id=subject.id,
        semantic_family=I10SemanticFamily.MORNING_CHECK_IN.value,
    )
    with patch(
        "backend.app.services.i10.intake.apply_i10_provider_lifetime",
        wraps=lambda db, candidate, now_utc=None: apply_i10_provider_lifetime(
            db, candidate, now_utc=now
        ),
    ):
        result = enqueue_i10_notification(db, candidate=cand, payload=payload)
    assert result.decision == I10DecisionValue.EXPIRE
    assert result.notification_id is None
    row = db.query(models.I10NotificationDecision).filter_by(id=result.decision_id).one()
    assert row.expires_at is not None
    assert row.decision == "EXPIRE"
    assert db.query(models.Notification).filter_by(user_id=user.id).count() == 0


def test_b_morning_fresh_window_remains_valid(db):
    user = _user(db, "morning-fresh", tz="Asia/Tehran")
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    now = datetime.now(timezone.utc)
    local = get_local_now(now, "Asia/Tehran")
    daily_time = f"{local.hour:02d}:{local.minute:02d}"
    db.add(models.NotificationPrefs(user_id=user.id, daily_notification_time=daily_time))
    db.commit()
    cand = _candidate(
        subject_id=subject.id,
        recipient_id=user.id,
        family=I10SemanticFamily.MORNING_CHECK_IN,
    )
    payload = NotificationPayload(
        user_id=user.id,
        type="morning_brief",
        title="T",
        body="B",
        priority="normal",
        dedupe_key=f"morning-fresh-{uuid4().hex}",
        health_subject_id=subject.id,
        semantic_family=I10SemanticFamily.MORNING_CHECK_IN.value,
    )
    result = enqueue_i10_notification(db, candidate=cand, payload=payload)
    assert result.decision == I10DecisionValue.SEND
    assert result.notification_id is not None
    row = db.query(models.I10NotificationDecision).filter_by(id=result.decision_id).one()
    assert row.expires_at is not None
    assert row.expires_at > now


def test_c_daily_wellness_expires_at_local_day_boundary(db):
    user = _user(db, "daily-bound", tz="Asia/Tehran")
    now = datetime(2026, 9, 25, 8, 30, tzinfo=timezone.utc)  # 12:00 Tehran
    cand = _candidate(subject_id=1, recipient_id=user.id, family=I10SemanticFamily.DAILY_WELLNESS_DIGEST)
    stamped = apply_i10_provider_lifetime(db, cand, now_utc=now)
    again = apply_i10_provider_lifetime(db, cand, now_utc=now)
    assert stamped.expires_at == again.expires_at
    # Next Tehran midnight = 2026-09-25 20:30 UTC
    assert stamped.expires_at == datetime(2026, 9, 25, 20, 30, tzinfo=timezone.utc)


def test_d_missing_i8_expiry_blocks_real_fcm(db, monkeypatch):
    user = _user(db, "miss-i8")
    decision = _decision(db, user, family=I10SemanticFamily.MEDICATION_DUE.value, expires_at=None)
    _queued(db, user, decision=decision, family=I10SemanticFamily.MEDICATION_DUE.value)
    sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    notif = db.query(models.Notification).one()
    assert sent == 0
    assert captured == []
    assert notif.status == "queued"
    assert notif.is_sent is False
    assert "MISSING_I8_SOURCE_EXPIRY" in (notif.last_error or "")
    refreshed = db.query(models.I10NotificationDecision).filter_by(id=decision.id).one()
    assert refreshed.expires_at is None
    assert refreshed.decision == "SEND"


def test_d_missing_i9_validity_blocks_real_fcm(db, monkeypatch):
    user = _user(db, "miss-i9")
    decision = _decision(db, user, family=I10SemanticFamily.DEVICE_STATUS.value, expires_at=None)
    _queued(db, user, decision=decision, family=I10SemanticFamily.DEVICE_STATUS.value)
    sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    notif = db.query(models.Notification).one()
    assert sent == 0
    assert captured == []
    assert "MISSING_I9_SOURCE_VALIDITY" in (notif.last_error or "")
    assert notif.status == "queued"


def test_d_missing_i4_safety_expiry_blocks_real_fcm(db, monkeypatch):
    user = _user(db, "miss-i4")
    decision = _decision(db, user, family=I10SemanticFamily.SAFETY_ESCALATION.value, expires_at=None)
    _queued(db, user, decision=decision, family=I10SemanticFamily.SAFETY_ESCALATION.value)
    sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    notif = db.query(models.Notification).one()
    assert sent == 0
    assert captured == []
    assert "MISSING_I4_SAFETY_EXPIRY" in (notif.last_error or "")
    assert notif.status == "queued"


def test_d_i10_does_not_fabricate_upstream_validity(db):
    user = _user(db, "no-fab")
    now = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
    for family in (
        I10SemanticFamily.MEDICATION_DUE,
        I10SemanticFamily.HR_INSTABILITY,
        I10SemanticFamily.CARE_SAFETY_ESCALATION,
    ):
        cand = _candidate(subject_id=1, recipient_id=user.id, family=family)
        stamped = apply_i10_provider_lifetime(db, cand, now_utc=now)
        assert stamped.expires_at is None


def test_e_fresh_adapter_may_send(db, monkeypatch):
    user = _user(db, "fresh-send")
    _android_token(db, user)
    now = datetime.now(timezone.utc)
    decision = _decision(
        db,
        user,
        family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value,
        expires_at=now + timedelta(hours=2),
    )
    _queued(db, user, decision=decision)
    sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    notif = db.query(models.Notification).one()
    assert sent == 1
    assert len(captured) == 1
    assert notif.status == "sent"
    assert notif.is_sent is True


def test_e_expired_not_sent_and_second_run_does_not_resend(db, monkeypatch):
    user = _user(db, "stale-exp")
    now = datetime.now(timezone.utc)
    decision = _decision(
        db,
        user,
        family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value,
        expires_at=now - timedelta(minutes=5),
        decision="SEND",
    )
    original_decision = decision.decision
    original_reason = decision.reason_code
    _queued(db, user, decision=decision)
    sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    notif = db.query(models.Notification).one()
    assert sent == 0
    assert captured == []
    assert notif.status == "expired"
    assert notif.is_sent is False
    assert notif.sent_at is None
    assert notif.status != "failed"
    assert notif.status != "sent"
    refreshed = db.query(models.I10NotificationDecision).filter_by(id=decision.id).one()
    assert refreshed.decision == original_decision
    assert refreshed.reason_code == original_reason
    sent2, captured2 = _deliver_via_fcm_adapter(db, monkeypatch)
    assert sent2 == 0
    assert captured2 == []
    notif2 = db.query(models.Notification).one()
    assert notif2.status == "expired"
    assert notif2.is_sent is False


def test_f_fresh_critical_may_preserve_quiet_hours_bypass(db, monkeypatch):
    user = _user(db, "crit-fresh")
    _android_token(db, user)
    now = datetime.now(timezone.utc)
    decision = _decision(
        db,
        user,
        family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value,
        expires_at=now + timedelta(hours=1),
    )
    _queued(
        db,
        user,
        decision=decision,
        priority="critical",
        risk_level="critical",
    )
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_delivery_with_gate4_policy",
        return_value=(True, MagicMock()),
    ):
        sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    assert sent == 1
    assert len(captured) == 1


def test_f_stale_critical_must_not_send(db, monkeypatch):
    user = _user(db, "crit-stale")
    now = datetime.now(timezone.utc)
    decision = _decision(
        db,
        user,
        family=I10SemanticFamily.PRESENCE_REENGAGEMENT.value,
        expires_at=now - timedelta(minutes=1),
    )
    _queued(
        db,
        user,
        decision=decision,
        priority="critical",
        risk_level="critical",
    )
    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_delivery_with_gate4_policy",
        return_value=(True, MagicMock()),
    ):
        sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    notif = db.query(models.Notification).one()
    assert sent == 0
    assert captured == []
    assert notif.status == "expired"
    assert notif.is_sent is False


def test_g_effective_fcm_ttl_capped_and_no_send_if_remaining_zero():
    assert compute_effective_fcm_ttl(
        remaining_provider_lifetime_seconds=90,
        transport_ttl_seconds=3600,
    ) == 90
    assert compute_effective_fcm_ttl(
        remaining_provider_lifetime_seconds=5000,
        transport_ttl_seconds=3600,
    ) == 3600
    assert compute_effective_fcm_ttl(
        remaining_provider_lifetime_seconds=120,
        transport_ttl_seconds=None,
    ) == 120
    assert compute_effective_fcm_ttl(
        remaining_provider_lifetime_seconds=0,
        transport_ttl_seconds=3600,
    ) == 0


def test_g_fcm_adapter_uses_capped_ttl_and_skips_expired(db, monkeypatch):
    monkeypatch.setenv(_GATE, "true")
    user = _user(db, "ttl-cap")
    now = datetime.now(timezone.utc)
    decision = _decision(
        db,
        user,
        family=I10SemanticFamily.ENGAGEMENT_NUDGE.value,
        expires_at=now + timedelta(seconds=90),
    )
    notif = _queued(db, user, decision=decision, ttl_seconds=3600)
    captured = {}

    def _fake_send(**kwargs):
        captured.update(kwargs)
        return (1, [(kwargs["tokens"][0], "mock", None)])

    db.add(
        models.PushDevice(
            user_id=user.id,
            platform="android",
            fcm_token=("fcm-fresh-" + "x" * 80)[:96],
            is_active=True,
        )
    )
    db.commit()
    adapter = FCMAdapter(db=db, timeout_sec=1)
    with patch(
        "backend.app.services.notifications.fcm_client.send_push_to_tokens",
        side_effect=_fake_send,
    ):
        ok = adapter.send(notif)
    assert ok is True
    assert captured["ttl_seconds"] is not None
    assert 1 <= int(captured["ttl_seconds"]) <= 90
    assert notif.ttl_seconds == 3600

    stale_decision = _decision(
        db,
        user,
        family=I10SemanticFamily.ENGAGEMENT_NUDGE.value,
        expires_at=now - timedelta(seconds=1),
    )
    stale = _queued(db, user, decision=stale_decision, ttl_seconds=3600)
    captured.clear()
    with patch(
        "backend.app.services.notifications.fcm_client.send_push_to_tokens",
        side_effect=_fake_send,
    ):
        ok2 = adapter.send(stale)
    assert ok2 is False
    assert captured == {}
    assert stale.status == "expired"
    assert stale.is_sent is False
    assert stale.sent_at is None


def test_h_provider_gate_unset_blocks_real_http(monkeypatch):
    monkeypatch.delenv(_GATE, raising=False)
    assert provider_delivery_enabled() is False
    from backend.app.services.notifications.fcm_client import send_push_to_tokens

    monkeypatch.delenv("FCM_DISABLED", raising=False)
    with patch("backend.app.services.notifications.fcm_client.requests.post") as post:
        count, results = send_push_to_tokens(
            tokens=["tok"],
            title="t",
            body="b",
            project_id="demo",
        )
    assert count == 0
    assert results[0][2] == "provider_delivery_disabled"
    assert post.call_count == 0


def test_h_i_send_now_cannot_bypass_gate_or_i10(client, db, monkeypatch):
    user = _user(db, "send-now")
    db.add(
        models.PushDevice(
            user_id=user.id,
            platform="android",
            fcm_token=("fcm-now-" + "x" * 80)[:96],
            is_active=True,
        )
    )
    db.commit()
    monkeypatch.setenv("ADMIN_TOKEN", "admin-fresh")
    monkeypatch.delenv(_GATE, raising=False)
    with patch("backend.app.services.notifications.fcm_client.send_push_to_tokens") as send:
        r = client.post(
            f"/notifications/admin/notif/send_now?user_id={user.id}&channel=engagement&force=true",
            headers={"X-Admin-Token": "admin-fresh"},
        )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["blocked"] is True
    assert "PROVIDER_DELIVERY_DISABLED" in body["reasons"]
    assert body["sent_success"] == 0
    assert send.call_count == 0

    monkeypatch.setenv(_GATE, "true")
    with patch("backend.app.services.notifications.fcm_client.send_push_to_tokens") as send2:
        r2 = client.post(
            f"/notifications/admin/notif/send_now?user_id={user.id}&channel=engagement&force=true",
            headers={"X-Admin-Token": "admin-fresh"},
        )
    assert r2.status_code == 200
    body2 = r2.json()["data"]
    assert body2["blocked"] is True
    assert "I10_PROVIDER_AUTHORITY_REQUIRED" in body2["reasons"]
    assert body2["sent_success"] == 0
    assert send2.call_count == 0


def test_j_language_contract_action_labels():
    assert get_action_label("ACK_THANKS", "fa") == ACTION_LABELS["ACK_THANKS"]["fa"]
    assert get_action_label("ACK_THANKS", "en") == ACTION_LABELS["ACK_THANKS"]["en"]
    assert get_action_label("ACK_THANKS", "ar") == ACTION_LABELS["ACK_THANKS"]["ar"]
    assert get_action_label("NOT_NOW", "fa") == ACTION_LABELS["NOT_NOW"]["fa"]
    assert get_action_label("NOT_NOW", "en") == ACTION_LABELS["NOT_NOW"]["en"]
    assert get_action_label("NOT_NOW", "ar") == ACTION_LABELS["NOT_NOW"]["ar"]
    assert get_action_label("TALK_LATER", "fa") == ACTION_LABELS["TALK_LATER"]["fa"]
    assert get_action_label("OPEN_CHAT", "ar") == ACTION_LABELS["OPEN_CHAT"]["ar"]
    assert get_action_label("ACK_THANKS", "zz") == ACTION_LABELS["ACK_THANKS"]["en"]
    assert normalize_language("de") == "en"
    for action in _CANONICAL_ACTIONS:
        assert action == action.upper()
        assert action.isascii()
        assert get_action_label(action, "fa") != action
        assert get_action_label(action, "en") != action
        assert get_action_label(action, "ar") != action


def test_k_templates_v1_ar_gaps_documented():
    missing_ar = []
    for tpl in TEMPLATES_V1:
        texts = tpl.get("texts") or {}
        if "ar" not in texts:
            missing_ar.append(tpl["key"])
    assert missing_ar == [
        "companion_daily_checkin_v1",
        "companion_encourage_move_v1",
        "companion_breathing_break_v1",
        "health_alert_generic_v1",
    ]


def test_a_unlinked_real_fcm_blocks_zero_http(db, monkeypatch):
    user = _user(db, "unlinked-real")
    _android_token(db, user)
    _queued(db, user)
    sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    notif = db.query(models.Notification).one()
    assert sent == 0
    assert captured == []
    assert notif.is_sent is False
    assert notif.status == "queued"
    assert "MISSING_I10_PROVIDER_AUTHORITY" in (notif.last_error or "")
    ev = evaluate_notification_provider_freshness(db, notif)
    assert ev.outcome == ProviderFreshnessOutcome.BLOCK
    assert ev.reason_code == "MISSING_I10_PROVIDER_AUTHORITY"


def test_b_counting_adapter_channel_fcm_is_not_real_provider(db, monkeypatch):
    monkeypatch.setenv(_GATE, "true")
    user = _user(db, "count-false")
    _queued(db, user)
    adapter = RecordingFCMAdapter()
    assert adapter.channel == "fcm"
    assert is_real_fcm_adapter(adapter) is False
    sent = DeliveryService(db=db, adapter=adapter).deliver_pending(limit=10)
    notif = db.query(models.Notification).one()
    assert sent == 1
    assert adapter.calls == 1
    assert notif.is_sent is True


def test_c_fcm_adapter_direct_call_cannot_bypass_i10(db, monkeypatch):
    monkeypatch.setenv(_GATE, "true")
    user = _user(db, "direct-fcm")
    _android_token(db, user)
    notif = _queued(db, user)
    captured = []

    def _fake_send(**kwargs):
        captured.append(kwargs)
        return (1, [(kwargs["tokens"][0], "mock", None)])

    adapter = FCMAdapter(db=db, timeout_sec=1)
    with patch(
        "backend.app.services.notifications.fcm_client.send_push_to_tokens",
        side_effect=_fake_send,
    ):
        ok = adapter.send(notif)
    assert ok is False
    assert captured == []
    assert notif.is_sent is False
    assert "MISSING_I10_PROVIDER_AUTHORITY" in (notif.last_error or "")


def test_test_push_provider_on_creates_no_row(client, db, monkeypatch):
    monkeypatch.setenv(_GATE, "true")
    monkeypatch.setenv("ADMIN_TOKEN", "admin-fresh")
    user = _user(db, "push-on")
    before = db.query(models.Notification).count()
    with patch.object(DeliveryService, "deliver_pending", return_value=99) as deliver:
        r = client.post(
            "/notifications/admin/test_push?deliver=true",
            headers={"X-Admin-Token": "admin-fresh"},
            json={"user_id": user.id, "channel": "engagement", "priority": "normal"},
        )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["blocked"] is True
    assert "TEST_PUSH_PROVIDER_ROW_BLOCKED" in body["reasons"]
    assert body["notification_id"] is None
    assert body["sent_count"] == 0
    assert deliver.call_count == 0
    assert db.query(models.Notification).count() == before


def test_test_push_legacy_row_cannot_cross_real_fcm_later(client, db, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-fresh")
    monkeypatch.delenv(_GATE, raising=False)
    user = _user(db, "push-legacy")
    _android_token(db, user)
    r = client.post(
        "/notifications/admin/test_push",
        headers={"X-Admin-Token": "admin-fresh"},
        json={"user_id": user.id, "channel": "engagement", "priority": "normal"},
    )
    assert r.status_code == 200
    notif_id = r.json()["data"]["notification_id"]
    assert notif_id is not None
    leftover = db.query(models.Notification).filter_by(id=notif_id).one()
    assert leftover.status == "queued"
    assert leftover.i10_policy_decision_id is None
    sent, captured = _deliver_via_fcm_adapter(db, monkeypatch)
    leftover = db.query(models.Notification).filter_by(id=notif_id).one()
    assert sent == 0
    assert captured == []
    assert leftover.is_sent is False
    assert leftover.status != "sent"
    assert "MISSING_I10_PROVIDER_AUTHORITY" in (leftover.last_error or "")


def test_provider_freshness_evaluate_does_not_mark_clinical_failure(db):
    user = _user(db, "not-clinical")
    result = evaluate_provider_freshness(
        db,
        family=I10SemanticFamily.MEDICATION_FOLLOW_UP,
        user_id=user.id,
        expires_at=None,
    )
    assert result.outcome == ProviderFreshnessOutcome.BLOCK
    assert result.reason_code == "MISSING_I8_SOURCE_EXPIRY"
    assert result.invented_validity is False
