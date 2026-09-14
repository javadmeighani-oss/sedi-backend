"""G2: I10 reachability hardening for legacy producer bypass candidates."""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func

from backend.app import models
from backend.app.services.gate5.ml_care_bridge import run_care_bridge
from backend.app.services.i10.policy_types import I10SemanticFamily
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
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


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}", preferred_language="en")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _self_setup(db, name: str):
    user = _user(db, name)
    subject = ensure_self_subject_for_account(db, user.id, commit=True)
    return user, subject


def _engine(db) -> DecisionEngine:
    return DecisionEngine(db)


def _no_direct_builder_persist_in_source(method_name: str) -> None:
    path = Path("backend/app/services/notification_engine.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "DecisionEngine":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    src = ast.get_source_segment(path.read_text(encoding="utf-8"), item) or ""
                    assert "builder.persist" not in src
                    assert "enqueue_self_scheduler_notification" in src
                    return
    raise AssertionError(f"method {method_name} not found")


def test_create_insight_routes_i10_and_no_direct_persist(db, gate4_patch):
    _no_direct_builder_persist_in_source("create_insight_notification")
    user, subject = _self_setup(db, "g2-insight")
    with patch.object(NotificationBuilder, "persist", wraps=NotificationBuilder(db).persist) as mock_persist:
        notif = _engine(db).create_insight_notification(user.id, "Gentle insight body")
    assert notif is not None
    assert notif.user_id == user.id
    assert notif.health_subject_id == subject.id
    assert notif.i10_policy_decision_id is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.ENGAGEMENT.value
    assert decision.recipient_user_id == user.id
    assert mock_persist.call_count >= 1


def test_create_insight_i10_suppress_prevents_persist(db, gate4_patch):
    user, _ = _self_setup(db, "g2-insight-suppress")
    with patch(
        "backend.app.services.i10.self_producer_adapter.enqueue_i10_notification",
    ) as mock_enqueue:
        from backend.app.services.i10.intake import I10IntakeResult
        from backend.app.services.i10.policy_types import I10DecisionValue

        mock_enqueue.return_value = I10IntakeResult(
            decision=I10DecisionValue.SUPPRESS,
            reason_code="TEST_SUPPRESS",
            decision_id=1,
            notification_id=None,
            recipient_kind="SELF",
        )
        notif = _engine(db).create_insight_notification(user.id, "should not persist")
    assert notif is None
    count = db.query(func.count(models.Notification.id)).filter(
        models.Notification.user_id == user.id
    ).scalar()
    assert count == 0


def test_evaluate_health_data_routes_i10(db, gate4_patch):
    _no_direct_builder_persist_in_source("evaluate_health_data")
    user, subject = _self_setup(db, "g2-health")
    health = models.HealthData(
        user_id=user.id,
        heart_rate="120",
        spo2="98",
        temperature="36.5",
        created_at=datetime.utcnow(),
    )
    db.add(health)
    db.commit()
    db.refresh(health)

    notif = _engine(db).evaluate_health_data(user.id, health)
    assert notif is not None
    assert notif.type == "health_alert"
    assert notif.health_subject_id == subject.id
    assert notif.i10_policy_decision_id is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.DEVICE_STATUS.value
    assert decision.recipient_user_id == user.id
    assert "Heart rate is elevated" in (notif.body or "")


def test_evaluate_health_data_normal_returns_none(db, gate4_patch):
    user, _ = _self_setup(db, "g2-health-normal")
    health = models.HealthData(
        user_id=user.id,
        heart_rate="72",
        spo2="98",
        temperature="36.5",
        created_at=datetime.utcnow(),
    )
    db.add(health)
    db.commit()
    assert _engine(db).evaluate_health_data(user.id, health) is None


def test_kc_notification_routes_i10(db, gate4_patch):
    from backend.app.routers.knowledge import _maybe_send_kc_notification

    user, subject = _self_setup(db, "g2-kc")
    data = {
        "question_type": "confirm_candidate",
        "display_title": "Quick check",
        "display_body": "Is this still true?",
        "candidate_id": 42,
    }
    out = _maybe_send_kc_notification(db, user.id, data, "en", in_app=True)
    assert out["attempted"] is True
    assert out["ok"] is True
    assert out.get("notification_id") is not None
    notif = db.query(models.Notification).filter(
        models.Notification.id == out["notification_id"]
    ).one()
    assert notif.type == "kc_confirm"
    assert notif.user_id == user.id
    assert notif.health_subject_id == subject.id
    assert notif.i10_policy_decision_id is not None
    assert notif.dedupe_key == f"kc_confirm:{user.id}:confirm_candidate:42"
    # Dedupe preserved
    out2 = _maybe_send_kc_notification(db, user.id, data, "en", in_app=True)
    assert out2["reason"] == "dedupe_skip"
    assert out2["notification_id"] == notif.id


def test_kc_i10_suppress_no_notification(db, gate4_patch):
    from backend.app.routers.knowledge import _maybe_send_kc_notification
    from backend.app.services.i10.intake import I10IntakeResult
    from backend.app.services.i10.policy_types import I10DecisionValue

    user, _ = _self_setup(db, "g2-kc-suppress")
    data = {
        "question_type": "confirm_candidate",
        "display_title": "Quick check",
        "display_body": "Is this still true?",
        "candidate_id": 7,
    }
    with patch(
        "backend.app.routers.knowledge.enqueue_i10_notification",
        create=True,
    ):
        # Patch where used after import inside function — patch module symbol path used at call time
        with patch(
            "backend.app.services.i10.intake.enqueue_i10_notification",
            return_value=I10IntakeResult(
                decision=I10DecisionValue.SUPPRESS,
                reason_code="TEST_SUPPRESS",
                decision_id=99,
                notification_id=None,
                recipient_kind="SELF",
            ),
        ):
            out = _maybe_send_kc_notification(db, user.id, data, "en", in_app=True)
    assert out["ok"] is True
    assert "i10_suppress" in out["reason"]
    count = db.query(func.count(models.Notification.id)).filter(
        models.Notification.user_id == user.id
    ).scalar()
    assert count == 0


def test_ml_care_bridge_notification_routes_i10(db, gate4_patch, monkeypatch):
    user, subject = _self_setup(db, "g2-ml")
    model = models.MlModelRegistry(
        model_name="g2-care",
        model_version="1",
        signal_family="vitals",
        input_type="features",
        status="research",
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    row = models.MlInferenceRecord(
        user_id=user.id,
        device_id="dev-1",
        model_id=model.id,
        output_type="care_suggestion_candidate",
        score=0.4,
        confidence=0.5,
        user_visible=False,
        features_summary_json={},
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    monkeypatch.setenv("SEDI_GATE5_ML_CARE_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("SEDI_GATE5_ML_NOTIFICATION_ENABLED", "1")

    result = run_care_bridge(db, row.id, dry_run=False)
    assert result.bridge_enabled is True
    assert result.notification_enabled is True
    assert result.notification_id is not None
    notif = db.query(models.Notification).filter(
        models.Notification.id == result.notification_id
    ).one()
    assert notif.type == "care_suggestion"
    assert notif.user_id == user.id
    assert notif.health_subject_id == subject.id
    assert notif.i10_policy_decision_id is not None
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.CARE_ACTION.value


def test_ml_care_bridge_i10_suppress_skips_notification(db, gate4_patch, monkeypatch):
    from backend.app.services.i10.intake import I10IntakeResult
    from backend.app.services.i10.policy_types import I10DecisionValue

    user, _ = _self_setup(db, "g2-ml-suppress")
    model = models.MlModelRegistry(
        model_name="g2-care-suppress",
        model_version="1",
        signal_family="vitals",
        input_type="features",
        status="research",
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    row = models.MlInferenceRecord(
        user_id=user.id,
        device_id="dev-2",
        model_id=model.id,
        output_type="possible_anomaly",
        score=0.4,
        confidence=0.5,
        user_visible=False,
        features_summary_json={},
        created_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    monkeypatch.setenv("SEDI_GATE5_ML_CARE_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("SEDI_GATE5_ML_NOTIFICATION_ENABLED", "1")

    with patch(
        "backend.app.services.i10.intake.enqueue_i10_notification",
        return_value=I10IntakeResult(
            decision=I10DecisionValue.SUPPRESS,
            reason_code="TEST_SUPPRESS",
            decision_id=1,
            notification_id=None,
            recipient_kind="SELF",
        ),
    ):
        result = run_care_bridge(db, row.id, dry_run=False)
    assert result.notification_id is None
    count = db.query(func.count(models.Notification.id)).filter(
        models.Notification.user_id == user.id
    ).scalar()
    assert count == 0


def test_static_no_orm_bypass_in_kc_and_ml_sources():
    kc = Path("backend/app/routers/knowledge.py").read_text(encoding="utf-8")
    assert "enqueue_i10_notification" in kc
    assert "models.Notification(" not in kc

    ml = Path("backend/app/services/gate5/ml_care_bridge.py").read_text(encoding="utf-8")
    assert "enqueue_i10_notification" in ml
    assert "Notification(\n            user_id=row.user_id" not in ml


def test_admin_test_push_untouched():
    src = Path("backend/app/routers/notifications.py").read_text(encoding="utf-8")
    assert "def admin_test_push" in src
    assert "admin_test_push" in src
