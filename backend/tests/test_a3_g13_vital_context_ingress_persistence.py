"""A3 G13 — vital context ingress persistence + shadow load (minimal)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from backend.app import models
from backend.app.services.i9.absolute_vital_observation import (
    CanonicalVitalObservation,
    SOURCE_CLASS_LEGACY_HEALTHDATA,
)
from backend.app.services.i9.absolute_vital_shadow_eligibility import (
    BLOCKED_CONFIRMATION,
    BLOCKED_MEASUREMENT_QUALITY,
    BLOCKED_MISSING_CONTEXT,
    BLOCKED_POLICY_NOT_APPROVED,
    evaluate_shadow_eligibility,
)
from backend.app.core.device_auth import hash_device_token
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.i9.vital_observation_context import (
    AuthorityState,
    resolve_vital_observation_context,
)
from backend.app.services.i9.vital_observation_context_persistence import (
    SOURCE_PHYSIOLOGICAL_MEASUREMENT,
    ContextPersistenceError,
    ContextPersistInput,
    persist_context_from_physiological_measurement,
    persist_vital_observation_context,
)
from backend.tests.helpers.i10_postgresql_harness import ALEMBIC_HEAD, I10IsolatedPgDb

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]


def test_g13_static_safety():
    src = Path("backend/app/services/i9/vital_observation_context_persistence.py").read_text(
        encoding="utf-8"
    )
    for token in ("37.5", "TACHYCARDIA", "FEVER", "enqueue_i10", "hr > 100"):
        assert token not in src
    assert ALEMBIC_HEAD == "086_i9_vital_observation_context_authority"


def test_g13_alembic_single_head_086():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == [ALEMBIC_HEAD]


def _make_device(db, *, user_id: int) -> models.Device:
    device = models.Device(
        user_id=user_id,
        device_id=f"SEDI-G13-{uuid4().hex[:10]}",
        device_type="heart_rate",
        status="active",
        token_hash=hash_device_token(f"tok-{uuid4().hex[:8]}"),
    )
    db.add(device)
    db.flush()
    return device


def test_g13_pg_pm_quality_persist_idempotent_shadow_and_boundaries():
    isolated = I10IsolatedPgDb.create(suffix="g13voc", revision=ALEMBIC_HEAD)
    Session = isolated.session_factory()
    db = Session()
    try:
        assert isolated.head() == ALEMBIC_HEAD
        when = datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc)

        user = models.User(
            name="G13User",
            secret_key="k-g13",
            preferred_language="en",
            phone="+989191130001",
        )
        other_user = models.User(
            name="G13Other",
            secret_key="k-g13o",
            preferred_language="en",
            phone="+989191130002",
        )
        db.add_all([user, other_user])
        db.commit()
        db.refresh(user)
        db.refresh(other_user)
        subject = ensure_self_subject_for_account(db, user.id, commit=True)
        other_hs = ensure_self_subject_for_account(db, other_user.id, commit=True)

        device = _make_device(db, user_id=user.id)
        pm = models.PhysiologicalMeasurement(
            user_id=user.id,
            health_subject_id=subject.id,
            device_id=device.id,
            measurement_type="heart_rate",
            numeric_value=72.0,
            unit="bpm",
            measured_at=when,
            received_at=when,
            quality_state="good",
            idempotency_key=f"g13-pm-{uuid4().hex}",
            ingestion_status="accepted",
        )
        db.add(pm)
        db.commit()
        db.refresh(pm)

        # A + D: explicit PM quality persists with provenance
        row1 = persist_context_from_physiological_measurement(db, pm, commit=True)
        assert row1 is not None
        assert row1.quality_state == "good"
        assert row1.activity_state is None
        assert row1.altitude_value is None
        assert row1.temperature_method is None
        assert row1.confirmation_state is None
        assert "physiological_measurements.quality_state" in (row1.context_authority_json or "")

        # B: retry idempotent
        row2 = persist_context_from_physiological_measurement(db, pm, commit=True)
        assert row2 is not None
        assert int(row2.id) == int(row1.id)
        assert db.execute(text("SELECT COUNT(*) FROM i9_vital_observation_contexts")).scalar_one() == 1

        # C: wrong / missing subject blocked
        with pytest.raises(ContextPersistenceError):
            persist_vital_observation_context(
                db,
                ContextPersistInput(
                    health_subject_id=9_999_999,
                    source_class=SOURCE_PHYSIOLOGICAL_MEASUREMENT,
                    source_row_id=int(pm.id),
                    physiological_measurement_id=int(pm.id),
                    metric="heart_rate",
                    observed_at=when,
                    quality_state="good",
                ),
            )
        with pytest.raises(ContextPersistenceError):
            persist_vital_observation_context(
                db,
                ContextPersistInput(
                    health_subject_id=int(other_hs.id),
                    source_class=SOURCE_PHYSIOLOGICAL_MEASUREMENT,
                    source_row_id=int(pm.id),
                    physiological_measurement_id=int(pm.id),
                    metric="heart_rate",
                    observed_at=when,
                    quality_state="good",
                ),
            )

        # E + L: same PM observation loads KNOWN quality into shadow path
        obs = CanonicalVitalObservation(
            metric="heart_rate",
            normalized_value=72.0,
            unit="bpm",
            measured_at=when,
            source_class="DEVICE",
            account_user_id=user.id,
            health_subject_id=subject.id,
            device_id=device.id,
            quality_state=None,
            provenance={
                "physiological_measurement_id": int(pm.id),
                "unit_authority": "test",
            },
            structural_parse_ok=True,
        )
        ctx = resolve_vital_observation_context(db, obs)
        assert ctx.quality_state.state == AuthorityState.KNOWN
        assert ctx.quality_state.value == "good"
        # G/H/I: missing activity/altitude/temp method stay UNKNOWN
        assert ctx.activity_state.state == AuthorityState.UNKNOWN
        assert ctx.altitude.state == AuthorityState.UNKNOWN
        assert ctx.temperature_method.state == AuthorityState.UNKNOWN
        assert ctx.confirmation_state.state == AuthorityState.UNKNOWN

        # F: HealthData quality remains UNKNOWN (no PM transfer)
        hd = models.HealthData(user_id=user.id, heart_rate="72", created_at=when)
        db.add(hd)
        db.commit()
        db.refresh(hd)
        obs_hd = CanonicalVitalObservation(
            metric="heart_rate",
            normalized_value=72.0,
            unit="bpm",
            measured_at=when,
            source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
            account_user_id=user.id,
            health_subject_id=subject.id,
            device_id=None,
            quality_state=None,
            provenance={"health_data_id": int(hd.id), "unit_authority": "test"},
            structural_parse_ok=True,
        )
        ctx_hd = resolve_vital_observation_context(db, obs_hd)
        assert ctx_hd.quality_state.state == AuthorityState.UNKNOWN

        # J: confirmation never inferred from multiple rows
        for i in range(3):
            db.add(
                models.HealthData(
                    user_id=user.id,
                    heart_rate="70",
                    created_at=when - timedelta(minutes=i + 1),
                )
            )
        db.commit()
        assert resolve_vital_observation_context(db, obs_hd).confirmation_state.state == AuthorityState.UNKNOWN

        # K: symptom ±24h heuristic not promoted to KNOWN
        db.add(
            models.HealthSymptomReport(
                user_id=user.id,
                reported_at=when.replace(tzinfo=None) - timedelta(hours=1),
                symptom_label="cough",
                severity="mild",
                status="active",
                source="api",
                created_at=when.replace(tzinfo=None),
            )
        )
        db.commit()
        ctx_sym = resolve_vital_observation_context(db, obs_hd)
        assert ctx_sym.symptom_refs.state == AuthorityState.UNKNOWN
        assert ctx_sym.symptom_refs.value["authority"] == "PARTIAL_HEURISTIC_NOT_CLINICAL"

        # L + M: shadow consumes persisted quality; numeric policy still blocks
        result = evaluate_shadow_eligibility(db, [obs], attach_context=True)
        assert result.eligible is False
        assert BLOCKED_POLICY_NOT_APPROVED in result.blockers
        assert BLOCKED_CONFIRMATION in result.blockers
        assert BLOCKED_MISSING_CONTEXT in result.blockers
        assert BLOCKED_MEASUREMENT_QUALITY not in result.observations[0].blockers

        # N: no notification side effect
        before = db.execute(text("SELECT COUNT(*) FROM notifications")).scalar_one()
        evaluate_shadow_eligibility(db, [obs])
        after = db.execute(text("SELECT COUNT(*) FROM notifications")).scalar_one()
        assert before == after
        assert db.execute(text("SELECT COUNT(*) FROM i9_absolute_vital_policies")).scalar_one() == 0
    finally:
        db.close()
        isolated.close()


def test_g13_no_persist_when_all_unknown():
    isolated = I10IsolatedPgDb.create(suffix="g13empty", revision=ALEMBIC_HEAD)
    Session = isolated.session_factory()
    db = Session()
    try:
        user = models.User(
            name="G13E", secret_key="k-g13e", preferred_language="en", phone="+989191130003"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        subject = ensure_self_subject_for_account(db, user.id, commit=True)
        out = persist_vital_observation_context(
            db,
            ContextPersistInput(
                health_subject_id=subject.id,
                source_class="LEGACY_HEALTHDATA",
                source_row_id=1,
                metric="heart_rate",
                observed_at=datetime.now(timezone.utc),
            ),
            commit=True,
        )
        assert out is None
        assert db.execute(text("SELECT COUNT(*) FROM i9_vital_observation_contexts")).scalar_one() == 0
    finally:
        db.close()
        isolated.close()
