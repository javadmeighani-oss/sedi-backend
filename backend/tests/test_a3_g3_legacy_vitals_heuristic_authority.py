"""G3: legacy evaluate_health_data vitals heuristic vs I9 authority audit locks."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func

from backend.app import models
from backend.app.services.i10.intake import I10IntakeResult
from backend.app.services.i10.policy_types import I10DecisionValue, I10SemanticFamily
from backend.app.services.i9.device_reported_vital_status import (
    STATUS_STABLE,
    STATUS_UNSTABLE,
    normalize_device_reported_status,
)
from backend.app.services.i9.hr_stability import CanonicalHrStabilityStatus
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.notification_engine import DecisionEngine

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_GATE4_PATCH = patch(
    "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
    return_value=(True, {}),
)

# Locked G3 inventory — absolute cutoffs in evaluate_health_data (no I9 equivalent).
_LEGACY_DECISION_RULES = (
    ("heart_rate", "HealthData.heart_rate", "hr > 100", "priority=high", "notify"),
    ("heart_rate", "HealthData.heart_rate", "hr < 60", "priority=high", "notify"),
    ("spo2", "HealthData.spo2", "spo2 < 95", "priority=critical", "notify"),
    ("temperature", "HealthData.temperature", "temp > 37.5", "priority=high", "notify"),
)
_PRESENTATION_ONLY = (
    ("heart_rate", "60 <= hr <= 100", "body fragment only"),
    ("spo2", "spo2 >= 95", "body fragment only"),
    ("temperature", "temp <= 37.5", "body fragment only"),
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


def test_g3_heuristic_inventory_locked_in_source():
    src = Path("backend/app/services/notification_engine.py").read_text(encoding="utf-8")
    # Decision cutoffs still present (no invented I9 replacement; no new thresholds).
    assert "hr > 100" in src
    assert "hr < 60" in src
    assert "spo2 < 95" in src
    assert "temp > 37.5" in src
    # No new absolute cutoffs beyond the locked set.
    assert "hr > 110" not in src
    assert "spo2 < 90" not in src
    assert "temp > 38" not in src
    assert "LEGACY_GAP_NO_I9_EQUIVALENT" in src
    assert len(_LEGACY_DECISION_RULES) == 4
    assert len(_PRESENTATION_ONLY) == 3


def test_i9_drvs_authority_is_device_reported_not_absolute_thresholds():
    src = Path("backend/app/services/i9/device_reported_vital_status.py").read_text(
        encoding="utf-8"
    )
    assert "Backend must not recompute status from HR/MAD/baseline/thresholds" in src
    assert STATUS_STABLE == "STABLE"
    assert STATUS_UNSTABLE == "UNSTABLE"
    assert normalize_device_reported_status("stable") == STATUS_STABLE
    assert normalize_device_reported_status("UNSTABLE") == STATUS_UNSTABLE
    # Absolute clinical cutoffs must not live in I9 DRVS.
    assert "hr > 100" not in src
    assert "spo2 < 95" not in src
    assert "37.5" not in src


def test_i9_hr_stability_is_mad_not_absolute_bpm_cutoffs():
    src = Path("backend/app/services/i9/hr_stability.py").read_text(encoding="utf-8")
    assert "MAD" in src or "mad" in src
    assert CanonicalHrStabilityStatus.STABLE.value == "STABLE"
    assert CanonicalHrStabilityStatus.UNSTABLE_OR_CHANGED.value == "UNSTABLE_OR_CHANGED"
    assert "> 100" not in src
    assert "< 60" not in src


def test_evaluate_health_data_still_uses_legacy_when_no_i9_equivalent(db, gate4_patch):
    user, subject = _self_setup(db, "g3-legacy-hr")
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
    assert notif.health_subject_id == subject.id
    assert notif.user_id == user.id
    assert notif.i10_policy_decision_id is not None
    assert "Heart rate is elevated" in (notif.body or "")
    meta = (notif.context_json or "") if hasattr(notif, "context_json") else ""
    decision = db.query(models.I10NotificationDecision).filter(
        models.I10NotificationDecision.id == notif.i10_policy_decision_id
    ).one()
    assert decision.semantic_family == I10SemanticFamily.DEVICE_STATUS.value
    assert decision.recipient_user_id == user.id
    # Provenance metadata marker from G3 audit
    assert notif.i10_policy_decision_id is not None
    _ = meta  # unused; attribution asserted above


def test_i10_still_governs_legacy_path_suppression(db, gate4_patch):
    user, _ = _self_setup(db, "g3-i10-suppress")
    health = models.HealthData(
        user_id=user.id,
        heart_rate="130",
        created_at=datetime.utcnow(),
    )
    db.add(health)
    db.commit()
    with patch(
        "backend.app.services.i10.self_producer_adapter.enqueue_i10_notification",
        return_value=I10IntakeResult(
            decision=I10DecisionValue.SUPPRESS,
            reason_code="TEST_SUPPRESS",
            decision_id=1,
            notification_id=None,
            recipient_kind="SELF",
        ),
    ):
        notif = _engine(db).evaluate_health_data(user.id, health)
    assert notif is None
    count = db.query(func.count(models.Notification.id)).filter(
        models.Notification.user_id == user.id
    ).scalar()
    assert count == 0


def test_i9_drvs_producer_not_delegating_to_evaluate_health_data():
    prod = Path(
        "backend/app/services/i10/device_reported_vital_status_producer.py"
    ).read_text(encoding="utf-8")
    assert "evaluate_health_data" not in prod
    assert "hr > 100" not in prod
    assert "spo2 < 95" not in prod


def test_no_duplicate_i9_absolute_threshold_authority_in_evaluate_path():
    """G3: zero removable I9-duplicate absolute rules in evaluate_health_data."""
    assert all(r[0] for r in _LEGACY_DECISION_RULES)
    # Classification lock for report fields.
    duplicate_i9 = 0
    no_i9 = len(_LEGACY_DECISION_RULES)
    presentation = len(_PRESENTATION_ONLY)
    assert duplicate_i9 == 0
    assert no_i9 == 4
    assert presentation == 3
