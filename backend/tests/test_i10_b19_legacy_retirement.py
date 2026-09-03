"""I10-B19 — legacy writer retirement + canonical path freeze (PostgreSQL)."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app import models
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.notification_engine import DecisionEngine, persist_health_alert_d1

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_I10_ROOT = Path(__file__).resolve().parents[1] / "app" / "services" / "i10"
_APP_ROOT = Path(__file__).resolve().parents[1] / "app"

# In-scope I10 product writers that must not construct Notification ORM directly.
_IN_SCOPE_NO_DIRECT_ORM = (
    _APP_ROOT / "behavior" / "service.py",
    _APP_ROOT / "services" / "section10" / "medication_stock_notification.py",
    _APP_ROOT / "services" / "gate4" / "user_chat_reminder.py",
)

_IN_SCOPE_NO_DIRECT_FCM = (
    _APP_ROOT / "behavior" / "service.py",
    _APP_ROOT / "services" / "notification_engine.py",
    _APP_ROOT / "services" / "gate4" / "user_chat_reminder.py",
    _APP_ROOT / "services" / "section10" / "medication_stock_notification.py",
    *_I10_ROOT.glob("*.py"),
)

_TWELVE_FAMILIES = (
    I10SemanticFamily.PRESENCE_REENGAGEMENT,
    I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP,
    I10SemanticFamily.MEDICATION_DUE,
    I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER,
    I10SemanticFamily.DAILY_WELLNESS_DIGEST,
    I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING,
    I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP,
    I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP,
    I10SemanticFamily.CARE_STATUS_DIGEST,
    I10SemanticFamily.CARE_DATA_GAP,
    I10SemanticFamily.CARE_ACTION,
    I10SemanticFamily.CARE_SAFETY_ESCALATION,
)

_FAMILY_PRODUCER_HINTS = {
    I10SemanticFamily.PRESENCE_REENGAGEMENT.value: "self_producer_adapter",
    I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP.value: "contextual_followup_i10_adapter",
    I10SemanticFamily.MEDICATION_DUE.value: "medication_i10_adapter",
    I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER.value: "event_reminder_i10_adapter",
    I10SemanticFamily.DAILY_WELLNESS_DIGEST.value: "daily_wellness_digest",
    I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING.value: "coaching_i10_adapter",
    I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP.value: "coaching_i10_adapter",
    I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP.value: "coaching_i10_adapter",
    I10SemanticFamily.CARE_STATUS_DIGEST.value: "care_digest_producer_worker",
    I10SemanticFamily.CARE_DATA_GAP.value: "care_digest_producer_worker",
    I10SemanticFamily.CARE_ACTION.value: "care_action_producer_worker",
    I10SemanticFamily.CARE_SAFETY_ESCALATION.value: "care_safety_producer_worker",
}


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _has_call(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == name:
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr == name:
                return True
    return False


def _has_notification_ctor(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "Notification":
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr == "Notification":
                return True
    return False


def test_in_scope_writers_have_no_direct_notification_orm():
    for path in _IN_SCOPE_NO_DIRECT_ORM:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not _has_notification_ctor(tree), f"direct Notification ORM in {path.name}"


def test_in_scope_producers_have_no_direct_fcm_bypass():
    forbidden = ("send_push_to_tokens", "DeliveryService", "messaging.send")
    for path in _IN_SCOPE_NO_DIRECT_FCM:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for name in ("send_push_to_tokens",):
            assert not _has_call(tree, name), f"{name} in {path.name}"
        # DeliveryService import in producers is a bypass; allow comments only.
        if "from backend.app.services.notifications.delivery_service import" in text:
            pytest.fail(f"DeliveryService import in producer {path.name}")
        if "firebase_admin.messaging" in text or "messaging.send(" in text:
            pytest.fail(f"direct FCM in {path.name}")


def test_twelve_families_have_canonical_producer_modules():
    for family in _TWELVE_FAMILIES:
        hint = _FAMILY_PRODUCER_HINTS[family.value]
        matches = list(_I10_ROOT.glob(f"*{hint}*")) + list(_I10_ROOT.glob(f"{hint}.py"))
        # hint may be exact filename stem
        path = _I10_ROOT / f"{hint}.py"
        assert path.exists() or matches, f"missing producer module for {family.value}"
        src = path.read_text(encoding="utf-8") if path.exists() else matches[0].read_text(encoding="utf-8")
        assert "enqueue_i10_notification" in src or "create_i10_caregiver_delivery_intent" in src


def test_device_disconnected_routes_through_i10(db):
    user = _user(db, "b19-device")
    ensure_self_subject_for_account(db, user.id, commit=True)
    engine = DecisionEngine(db)
    with patch.dict("os.environ", {}, clear=False):
        notif = engine.create_device_disconnected(
            user_id=user.id,
            device_id="dev-b19-1",
            scheduled_for=datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None),
        )
    assert notif is not None
    assert notif.semantic_family == I10SemanticFamily.DEVICE_STATUS.value
    assert notif.health_subject_id is not None
    assert notif.i10_policy_decision_id is not None


def test_health_alert_routes_through_i10(db):
    user = _user(db, "b19-alert")
    ensure_self_subject_for_account(db, user.id, commit=True)
    engine = DecisionEngine(db)
    notif = engine.create_health_alert(user_id=user.id, alert_code="b19_rule", alert_reason="test")
    assert notif is not None
    assert notif.semantic_family == I10SemanticFamily.DEVICE_STATUS.value
    assert notif.i10_policy_decision_id is not None


def test_persist_health_alert_d1_routes_through_i10(db):
    user = _user(db, "b19-d1")
    ensure_self_subject_for_account(db, user.id, commit=True)
    notif = persist_health_alert_d1(
        db,
        user_id=user.id,
        title="Alert",
        body="Body",
        dedupe_key=f"b19-d1-{user.id}",
    )
    assert notif is not None
    assert notif.i10_policy_decision_id is not None


def test_user_chat_reminder_routes_through_i10(db):
    from backend.app.services.gate4.user_chat_reminder import create_user_chat_reminder

    user = _user(db, "b19-reminder")
    ensure_self_subject_for_account(db, user.id, commit=True)
    result = create_user_chat_reminder(
        db,
        user_id=user.id,
        message="tomorrow at 9:00 take a walk",
        now_utc=datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc),
    )
    assert result.get("created") is True
    notif = db.query(models.Notification).filter(models.Notification.id == result["notification_id"]).one()
    assert notif.semantic_family == I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP.value
    assert notif.i10_policy_decision_id is not None


def test_medication_stock_writer_retired():
    from types import SimpleNamespace

    from backend.app.services.section10.medication_stock_notification import (
        maybe_create_stock_notification,
    )

    um = SimpleNamespace(user_id=1, id=1, remaining_quantity=None, refill_threshold=None)
    assert maybe_create_stock_notification(None, um, bucket="2026-09-03") is None


def test_alembic_head_unchanged():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["077_i10_medication_adherence_foundation"]
