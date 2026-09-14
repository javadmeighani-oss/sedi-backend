"""A3 G9 — HealthData→I9 observation adapter + nonnumeric shadow eligibility."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from backend.app import models
from backend.app.services.i9.absolute_vital_observation import (
    SOURCE_CLASS_LEGACY_HEALTHDATA,
    CanonicalVitalObservation,
    adapt_health_data_to_observations,
)
from backend.app.services.i9.absolute_vital_shadow_eligibility import (
    BLOCKED_CONFIRMATION,
    BLOCKED_INVALID_STRUCTURAL_VALUE,
    BLOCKED_MEASUREMENT_QUALITY,
    BLOCKED_MISSING_CONTEXT,
    BLOCKED_POLICY_NOT_APPROVED,
    BLOCKED_PROVENANCE,
    BLOCKED_SUBJECT_AUTHORITY,
    BLOCKED_UNIT_AUTHORITY,
    BLOCKED_UNSUPPORTED_METRIC,
    ELIGIBLE_FOR_FUTURE_NUMERIC_EVALUATION,
    NUMERIC_POLICY_AUTHORIZED,
    evaluate_health_data_shadow_eligibility,
    evaluate_observation_eligibility,
    evaluate_shadow_eligibility,
)
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.notification_engine import DecisionEngine
from backend.tests.helpers.i10_postgresql_harness import ALEMBIC_HEAD, I10IsolatedPgDb

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_G9_FILES = (
    Path("backend/app/services/i9/absolute_vital_observation.py"),
    Path("backend/app/services/i9/absolute_vital_shadow_eligibility.py"),
)

_FORBIDDEN_CLINICAL = (
    "TACHYCARDIA",
    "BRADYCARDIA",
    "HYPOXEMIA",
    "FEVER",
    "GOVERNED_ALERT",
    "URGENT",
    "ABNORMAL",
)
_FORBIDDEN_THRESHOLDS = ("100", "60", "95", "37.5", "50", "120", "38", "39.5")


def _hd(
    *,
    user_id: int = 1,
    heart_rate: str | None = "72",
    spo2: str | None = None,
    temperature: str | None = None,
    health_id: int = 42,
    created_at: datetime | None = None,
) -> models.HealthData:
    row = models.HealthData(
        user_id=user_id,
        heart_rate=heart_rate,
        spo2=spo2,
        temperature=temperature,
        created_at=created_at or datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
    )
    row.id = health_id
    return row


def test_g9_static_no_clinical_or_threshold_logic():
    assert NUMERIC_POLICY_AUTHORIZED is False
    for path in _G9_FILES:
        src = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_CLINICAL:
            assert token not in src
        for token in ("37.5", "39.5"):
            assert token not in src
        for token in ("100", "60", "95", "50", "120", "38"):
            assert f"'{token}'" not in src
            assert f'"{token}"' not in src
            assert f" > {token}" not in src
            assert f" < {token}" not in src
        assert "enqueue_i10" not in src
        assert "Notification(" not in src
        assert "alert_results" not in src.lower() or "Does NOT persist" in src or "alert_results_persisted" in src


def test_g9_a_b_c_structural_adapt_hr_spo2_temp_no_clinical():
    db = MagicMock()
    with patch(
        "backend.app.services.i9.absolute_vital_observation.resolve_self_health_subject_id",
        return_value=7,
    ):
        obs = adapt_health_data_to_observations(
            db,
            _hd(heart_rate="80", spo2="97", temperature="36.8"),
        )
    metrics = {o.metric: o for o in obs}
    assert set(metrics) == {"heart_rate", "spo2", "temperature"}
    assert metrics["heart_rate"].normalized_value == 80.0
    assert metrics["heart_rate"].unit == "bpm"
    assert metrics["spo2"].normalized_value == 97.0
    assert metrics["spo2"].unit == "percent"
    assert metrics["temperature"].normalized_value == 36.8
    assert metrics["temperature"].unit == "C"
    for o in obs:
        assert o.source_class == SOURCE_CLASS_LEGACY_HEALTHDATA
        assert o.quality_state is None
        assert o.device_id is None
        assert o.provenance["health_data_id"] == 42
        assert o.provenance["healthdata_pm_dual_write"] == "DEFERRED"
        assert o.structural_parse_ok is True


def test_g9_d_subject_authority_fail_closed():
    db = MagicMock()
    with patch(
        "backend.app.services.i9.absolute_vital_observation.resolve_self_health_subject_id",
        return_value=None,
    ):
        obs = adapt_health_data_to_observations(db, _hd(heart_rate="70"))
    assert obs[0].health_subject_id is None
    elig = evaluate_observation_eligibility(obs[0])
    assert BLOCKED_SUBJECT_AUTHORITY in elig.blockers


def test_g9_e_missing_provenance_blocks():
    obs = CanonicalVitalObservation(
        metric="heart_rate",
        normalized_value=70.0,
        unit="bpm",
        measured_at=datetime.now(timezone.utc),
        source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
        account_user_id=1,
        health_subject_id=9,
        device_id=None,
        quality_state="ok",
        provenance={"unit_authority": "test", "confirmation_authority": True, "context": {
            "resting_or_activity_or_sleep": "resting",
        }},
        structural_parse_ok=True,
    )
    elig = evaluate_observation_eligibility(obs)
    assert BLOCKED_PROVENANCE in elig.blockers


def test_g9_f_unit_authority_blocks_without_guessing():
    obs = CanonicalVitalObservation(
        metric="heart_rate",
        normalized_value=70.0,
        unit=None,
        measured_at=datetime.now(timezone.utc),
        source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
        account_user_id=1,
        health_subject_id=9,
        device_id=None,
        quality_state="ok",
        provenance={"health_data_id": 1},
        structural_parse_ok=True,
    )
    elig = evaluate_observation_eligibility(obs)
    assert BLOCKED_UNIT_AUTHORITY in elig.blockers


def test_g9_g_h_i_quality_confirmation_context_block():
    db = MagicMock()
    with patch(
        "backend.app.services.i9.absolute_vital_observation.resolve_self_health_subject_id",
        return_value=3,
    ):
        obs = adapt_health_data_to_observations(db, _hd(heart_rate="72", spo2="96", temperature="36.6"))
    for o in obs:
        elig = evaluate_observation_eligibility(o)
        assert BLOCKED_MEASUREMENT_QUALITY in elig.blockers
        assert BLOCKED_CONFIRMATION in elig.blockers
        assert BLOCKED_MISSING_CONTEXT in elig.blockers


def test_g9_j_numeric_policy_always_blocked():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    # Even a fully governed observation remains blocked without numeric PO approval.
    obs = CanonicalVitalObservation(
        metric="heart_rate",
        normalized_value=70.0,
        unit="bpm",
        measured_at=datetime.now(timezone.utc),
        source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
        account_user_id=1,
        health_subject_id=9,
        device_id=None,
        quality_state="device_packet",
        provenance={
            "health_data_id": 1,
            "unit_authority": "test",
            "confirmation_authority": "explicit_test",
            "context": {"resting_or_activity_or_sleep": "resting"},
        },
        structural_parse_ok=True,
    )
    assert evaluate_observation_eligibility(obs).blockers == ()
    result = evaluate_shadow_eligibility(db, [obs])
    assert result.numeric_policy_authorized is False
    assert BLOCKED_POLICY_NOT_APPROVED in result.blockers
    assert result.final_state == BLOCKED_POLICY_NOT_APPROVED
    assert result.eligible is False
    assert result.final_state != ELIGIBLE_FOR_FUTURE_NUMERIC_EVALUATION


def test_g9_invalid_and_unsupported_metric():
    bad = CanonicalVitalObservation(
        metric="heart_rate",
        normalized_value=None,
        unit=None,
        measured_at=None,
        source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
        account_user_id=1,
        health_subject_id=1,
        device_id=None,
        quality_state=None,
        provenance={"health_data_id": 1},
        structural_parse_ok=False,
    )
    assert BLOCKED_INVALID_STRUCTURAL_VALUE in evaluate_observation_eligibility(bad).blockers
    unsupported = CanonicalVitalObservation(
        metric="glucose",
        normalized_value=100.0,
        unit="mg/dL",
        measured_at=datetime.now(timezone.utc),
        source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
        account_user_id=1,
        health_subject_id=1,
        device_id=None,
        quality_state="ok",
        provenance={"health_data_id": 1, "unit_authority": "x"},
        structural_parse_ok=True,
    )
    assert BLOCKED_UNSUPPORTED_METRIC in evaluate_observation_eligibility(unsupported).blockers


def test_g9_l_no_notification_i10_side_effect():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch(
        "backend.app.services.i9.absolute_vital_observation.resolve_self_health_subject_id",
        return_value=1,
    ), patch(
        "backend.app.services.i10.intake.enqueue_i10_notification"
    ) as enqueue, patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy"
    ) as gate4:
        result = evaluate_health_data_shadow_eligibility(db, _hd(heart_rate="110"))
        assert result.diagnostics["i10_side_effects"] is False
        assert result.diagnostics["alert_results_persisted"] is False
        enqueue.assert_not_called()
        gate4.assert_not_called()
        db.add.assert_not_called()
        db.commit.assert_not_called()


def test_g9_m_legacy_evaluate_health_unchanged_and_no_g9_hook():
    src = Path("backend/app/services/notification_engine.py").read_text(encoding="utf-8")
    health_src = Path("backend/app/routers/health.py").read_text(encoding="utf-8")
    assert "absolute_vital_shadow" not in src
    assert "absolute_vital_observation" not in src
    assert "absolute_vital_shadow" not in health_src
    assert "absolute_vital_observation" not in health_src
    assert "hr > 100" in src  # legacy path preserved


def test_g9_pg_subject_resolver_and_empty_g8_tables():
    isolated = I10IsolatedPgDb.create(suffix="g9elig", revision=ALEMBIC_HEAD)
    Session = isolated.session_factory()
    db = Session()
    try:
        assert isolated.head() == ALEMBIC_HEAD
        user = models.User(
            name="G9User",
            secret_key="k-g9",
            preferred_language="en",
            phone="+989191900001",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        hd_missing = models.HealthData(
            user_id=user.id,
            heart_rate="72",
            created_at=datetime.now(timezone.utc),
        )
        db.add(hd_missing)
        db.commit()
        db.refresh(hd_missing)

        result_missing = evaluate_health_data_shadow_eligibility(db, hd_missing)
        assert BLOCKED_SUBJECT_AUTHORITY in result_missing.blockers
        assert BLOCKED_POLICY_NOT_APPROVED in result_missing.blockers
        assert BLOCKED_MEASUREMENT_QUALITY in result_missing.blockers
        assert BLOCKED_CONFIRMATION in result_missing.blockers
        assert BLOCKED_MISSING_CONTEXT in result_missing.blockers

        ensure_self_subject_for_account(db, user.id, commit=True)
        hd = models.HealthData(
            user_id=user.id,
            heart_rate="72",
            spo2="98",
            temperature="36.7",
            created_at=datetime.now(timezone.utc),
        )
        db.add(hd)
        db.commit()
        db.refresh(hd)

        obs = adapt_health_data_to_observations(db, hd)
        assert len(obs) == 3
        assert all(o.health_subject_id is not None for o in obs)

        result = evaluate_health_data_shadow_eligibility(db, hd)
        assert result.eligible is False
        assert BLOCKED_POLICY_NOT_APPROVED in result.blockers
        assert result.numeric_policy_authorized is False

        # G8 tables remain unseeded by G9
        assert db.execute(text("SELECT COUNT(*) FROM i9_absolute_vital_policies")).scalar_one() == 0
        assert db.execute(text("SELECT COUNT(*) FROM i9_absolute_vital_policy_rules")).scalar_one() == 0
        assert db.execute(text("SELECT COUNT(*) FROM i9_absolute_vital_alert_results")).scalar_one() == 0

        # No notifications created by shadow path
        before = db.execute(text("SELECT COUNT(*) FROM notifications")).scalar_one()
        evaluate_health_data_shadow_eligibility(db, hd)
        after = db.execute(text("SELECT COUNT(*) FROM notifications")).scalar_one()
        assert before == after
    finally:
        db.close()
        isolated.close()


def test_g9_legacy_evaluate_still_routes_when_shadow_would_block(db):
    """Legacy clinical path unchanged; shadow does not suppress it."""
    user = models.User(
        name="G9Legacy",
        secret_key="k-g9l",
        preferred_language="en",
        phone="+989191900002",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_self_subject_for_account(db, user.id, commit=True)
    hd = models.HealthData(
        user_id=user.id,
        heart_rate="110",
        spo2="98",
        temperature="36.6",
        created_at=datetime.utcnow(),
    )
    db.add(hd)
    db.commit()
    db.refresh(hd)

    shadow = evaluate_health_data_shadow_eligibility(db, hd)
    assert shadow.eligible is False
    assert BLOCKED_POLICY_NOT_APPROVED in shadow.blockers

    with patch(
        "backend.app.services.gate4.policy_resolver.evaluate_enqueue_with_gate4_policy",
        return_value=(True, {}),
    ):
        out = DecisionEngine(db).evaluate_health_data(user.id, hd)
    assert out is not None
    assert out.type == "health_alert"
    assert "Heart rate is elevated" in (out.body or "")
