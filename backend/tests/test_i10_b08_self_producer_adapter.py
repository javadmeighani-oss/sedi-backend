"""I10-B08 SELF legacy producer adapter — morning, inactivity, engagement (PostgreSQL)."""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func

from backend.app import models
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.notification_engine import DecisionEngine, NotificationBuilder

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)


@pytest.fixture
def gate4_patch():
    with _GATE4_PATCH:
        yield


def _user(db, name: str, *, lang: str = "en") -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language=lang)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _self_setup(db, name: str = "self-user") -> tuple[models.User, models.HealthSubject]:
    user = _user(db, name)
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    return user, subject


def _engine(db) -> DecisionEngine:
    return DecisionEngine(db)


def test_morning_eligible_uses_i10_intake(db, gate4_patch):
    user, subject = _self_setup(db)
    when = datetime(2026, 8, 31, 9, 0, 0)
    with patch.object(NotificationBuilder, "persist", wraps=NotificationBuilder(db).persist) as mock_persist:
        notif = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    assert notif is not None
    assert notif.i10_policy_decision_id is not None
    assert notif.health_subject_id == subject.id
    assert notif.user_id == user.id
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.MORNING_CHECK_IN.value
    assert mock_persist.call_count >= 1


def test_morning_exactly_one_notification(db, gate4_patch):
    user, _ = _self_setup(db)
    when = datetime(2026, 8, 31, 9, 0, 0)
    _engine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    count = db.query(func.count(models.Notification.id)).filter(models.Notification.user_id == user.id).scalar()
    assert count == 1


def test_morning_decision_ledger_created(db, gate4_patch):
    user, subject = _self_setup(db)
    when = datetime(2026, 8, 31, 9, 0, 0)
    notif = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    row = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.notification_id == notif.id
    ).one()
    assert row.health_subject_id == subject.id
    assert row.recipient_user_id == user.id


def test_morning_same_occurrence_duplicate_blocked(db, gate4_patch):
    user, _ = _self_setup(db)
    when = datetime(2026, 8, 31, 9, 0, 0)
    first = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    second = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=when)
    assert first is not None
    assert second is None
    count = db.query(func.count(models.Notification.id)).filter(models.Notification.user_id == user.id).scalar()
    assert count == 1


def test_morning_next_day_allowed(db, gate4_patch):
    user, _ = _self_setup(db)
    d1 = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 9, 0, 0))
    d2 = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=datetime(2026, 9, 1, 9, 0, 0))
    assert d1 is not None and d2 is not None
    assert d1.id != d2.id


def test_morning_no_parallel_legacy_persist(db, gate4_patch):
    user, _ = _self_setup(db)
    engine = _engine(db)
    with patch.object(engine.builder, "persist") as mock_legacy:
        notif = engine.create_morning_brief(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 9, 0, 0))
    assert notif is not None
    mock_legacy.assert_not_called()


def test_inactivity_eligible_uses_i10(db, gate4_patch):
    user, subject = _self_setup(db)
    when = datetime(2026, 8, 31, 12, 0, 0)
    notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=when)
    assert notif is not None
    assert notif.type == "connection_ping"
    assert notif.health_subject_id == subject.id
    assert notif.i10_policy_decision_id is not None


def test_inactivity_non_medical_semantics(db, gate4_patch):
    user, _ = _self_setup(db)
    notif = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 12, 0, 0))
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.PRESENCE_REENGAGEMENT.value
    combined = f"{notif.title or ''} {notif.body or ''}".lower()
    for term in ("diagnosis", "unwell", "medical risk", "depression", "anxiety"):
        assert term not in combined


def test_inactivity_duplicate_same_occurrence_blocked(db, gate4_patch):
    user, _ = _self_setup(db)
    when = datetime(2026, 8, 31, 12, 0, 0)
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=when) is not None
    assert _engine(db).create_connection_ping(user_id=user.id, scheduled_for=when) is None


def test_inactivity_later_occurrence_allowed(db, gate4_patch):
    user, _ = _self_setup(db)
    n1 = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 12, 0, 0))
    n2 = _engine(db).create_connection_ping(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 16, 0, 0))
    assert n1 is not None and n2 is not None
    assert n1.id != n2.id


def test_inactivity_no_parallel_legacy_persist(db, gate4_patch):
    user, _ = _self_setup(db)
    engine = _engine(db)
    with patch.object(engine.builder, "persist") as mock_legacy:
        engine.create_connection_ping(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 12, 0, 0))
    mock_legacy.assert_not_called()


def test_inactivity_recent_interaction_suppression_preserved():
    from backend.app.core import scheduler as sched

    assert sched.INACTIVE_HOURS == 4


def test_engagement_nudge_uses_i10(db, gate4_patch):
    user, subject = _self_setup(db)
    when = datetime(2026, 8, 31, 15, 0, 0)
    notif = _engine(db).create_engagement_nudge(user_id=user.id, scheduled_for=when)
    assert notif is not None
    assert notif.health_subject_id == subject.id
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.ENGAGEMENT_NUDGE.value


def test_engagement_no_parallel_legacy_persist(db, gate4_patch):
    user, _ = _self_setup(db)
    engine = _engine(db)
    with patch.object(engine.builder, "persist") as mock_legacy:
        engine.create_engagement_nudge(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 15, 0, 0))
    mock_legacy.assert_not_called()


def test_engagement_per_occurrence_dedupe(db, gate4_patch):
    user, _ = _self_setup(db)
    when = datetime(2026, 8, 31, 15, 0, 0)
    assert _engine(db).create_engagement_nudge(user_id=user.id, scheduled_for=when) is not None
    assert _engine(db).create_engagement_nudge(user_id=user.id, scheduled_for=when) is None


def test_self_recipient_account(db, gate4_patch):
    user, subject = _self_setup(db)
    notif = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 9, 0, 0))
    assert notif.user_id == user.id
    assert notif.health_subject_id == subject.id


def test_self_subject_not_managed_substitute(db, gate4_patch):
    owner = _user(db, "owner")
    managed = create_managed_subject_without_account(db, account_user_id=owner.id, display_name="Parent")
    self_subj = ensure_self_subject_for_account(db, owner.id, commit=True)
    notif = _engine(db).create_morning_brief(user_id=owner.id, scheduled_for=datetime(2026, 8, 31, 9, 0, 0))
    assert notif.health_subject_id == self_subj.id
    assert notif.health_subject_id != managed.id


def test_no_caregiver_grant_required_for_self(db, gate4_patch):
    user, _ = _self_setup(db)
    grants = db.query(models.HealthSubjectNotificationGrant).filter(
        models.HealthSubjectNotificationGrant.recipient_user_id == user.id
    ).count()
    assert grants == 0
    assert _engine(db).create_morning_brief(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 9, 0, 0)) is not None


def test_source_notification_id_compatible(db, gate4_patch):
    user, _ = _self_setup(db)
    notif = _engine(db).create_morning_brief(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 9, 0, 0))
    assert notif.id is not None
    assert notif.user_id == user.id


def test_b08_no_rag_in_adapter():
    root = Path(__file__).resolve().parents[1] / "app" / "services" / "i10" / "self_producer_adapter.py"
    dumped = ast.dump(ast.parse(root.read_text(encoding="utf-8"))).lower()
    assert "rag" not in dumped


def test_b08_adapter_no_direct_fcm(db, gate4_patch):
    user, _ = _self_setup(db)
    with patch("backend.app.services.notifications.delivery_service.FCMAdapter.send") as mock_fcm:
        _engine(db).create_morning_brief(user_id=user.id, scheduled_for=datetime(2026, 8, 31, 9, 0, 0))
    mock_fcm.assert_not_called()


def test_occurrence_keys_not_forever_static():
    from backend.app.services.i10.self_producer_adapter import build_self_occurrence_key

    d1 = datetime(2026, 8, 31, 9, 0, 0)
    d2 = datetime(2026, 9, 1, 9, 0, 0)
    k1 = build_self_occurrence_key("morning", user_id=1, scheduled_for=d1)
    k2 = build_self_occurrence_key("morning", user_id=1, scheduled_for=d2)
    assert k1 != k2
