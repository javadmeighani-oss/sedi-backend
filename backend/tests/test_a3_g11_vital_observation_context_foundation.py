"""A3 G11 — VitalObservationContext foundation + fail-closed eligibility wiring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from backend.app import models
from backend.app.services.i9.absolute_vital_observation import (
    CanonicalVitalObservation,
    SOURCE_CLASS_LEGACY_HEALTHDATA,
    adapt_health_data_to_observations,
)
from backend.app.services.i9.absolute_vital_shadow_eligibility import (
    BLOCKED_CONFIRMATION,
    BLOCKED_MEASUREMENT_QUALITY,
    BLOCKED_MISSING_CONTEXT,
    BLOCKED_POLICY_NOT_APPROVED,
    evaluate_health_data_shadow_eligibility,
    evaluate_observation_eligibility,
    evaluate_shadow_eligibility,
)
from backend.app.services.i9.health_subject_service import (
    create_managed_subject_without_account,
    ensure_self_subject_for_account,
)
from backend.app.services.i9.vital_observation_context import (
    AuthorityState,
    resolve_vital_observation_context,
)
from backend.tests.helpers.i10_postgresql_harness import ALEMBIC_HEAD, I10IsolatedPgDb

pytest_plugins = ["backend.tests.helpers.i10_postgresql_harness"]

_G11 = Path("backend/app/services/i9/vital_observation_context.py")


def test_g11_static_no_thresholds_or_clinical_labels():
    src = _G11.read_text(encoding="utf-8")
    for token in ("TACHYCARDIA", "BRADYCARDIA", "HYPOXEMIA", "FEVER", "URGENT", "37.5", "39.5"):
        assert token not in src
    for token in ("100", "60", "95", "50", "120", "38"):
        assert f"'{token}'" not in src
        assert f" > {token}" not in src
    assert "enqueue_i10" not in src


def test_g11_alembic_head_unchanged():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("backend/alembic.ini")
    cfg.set_main_option("script_location", "backend/alembic")
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert heads == ["085_i9_absolute_vital_policy_schema_scaffold"]
    assert ALEMBIC_HEAD == "085_i9_absolute_vital_policy_schema_scaffold"


def _obs(*, user_id=1, subject_id=1, when=None, metric="heart_rate") -> CanonicalVitalObservation:
    return CanonicalVitalObservation(
        metric=metric,
        normalized_value=72.0,
        unit="bpm" if metric == "heart_rate" else ("percent" if metric == "spo2" else "C"),
        measured_at=when or datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
        source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
        account_user_id=user_id,
        health_subject_id=subject_id,
        device_id=None,
        quality_state=None,
        provenance={
            "health_data_id": 1,
            "unit_authority": "test",
        },
        structural_parse_ok=True,
    )


def test_g11_pg_context_contract_and_symptom_subject_boundary():
    isolated = I10IsolatedPgDb.create(suffix="g11ctx", revision=ALEMBIC_HEAD)
    Session = isolated.session_factory()
    db = Session()
    try:
        when = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        user_a = models.User(
            name="G11A", secret_key="k-g11a", preferred_language="en", phone="+989191110001"
        )
        user_b = models.User(
            name="G11B", secret_key="k-g11b", preferred_language="en", phone="+989191110002"
        )
        db.add_all([user_a, user_b])
        db.commit()
        db.refresh(user_a)
        db.refresh(user_b)
        self_a = ensure_self_subject_for_account(db, user_a.id, commit=True)
        managed = create_managed_subject_without_account(
            db, account_user_id=user_a.id, display_name="Other", commit=True
        )

        # Symptom on A near observation time
        db.add(
            models.HealthSymptomReport(
                user_id=user_a.id,
                reported_at=when.replace(tzinfo=None) - timedelta(hours=1),
                symptom_label="shortness of breath",
                severity="mild",
                status="active",
                source="api",
                created_at=when.replace(tzinfo=None),
            )
        )
        # Symptom on B must not attach to A
        db.add(
            models.HealthSymptomReport(
                user_id=user_b.id,
                reported_at=when.replace(tzinfo=None) - timedelta(hours=1),
                symptom_label="other user symptom",
                severity="mild",
                status="active",
                source="api",
                created_at=when.replace(tzinfo=None),
            )
        )
        db.commit()

        obs_self = _obs(user_id=user_a.id, subject_id=self_a.id, when=when, metric="spo2")
        obs_self = CanonicalVitalObservation(
            metric="spo2",
            normalized_value=96.0,
            unit="percent",
            measured_at=when,
            source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
            account_user_id=user_a.id,
            health_subject_id=self_a.id,
            device_id=None,
            quality_state=None,
            provenance={"health_data_id": 9, "unit_authority": "test"},
            structural_parse_ok=True,
        )
        ctx = resolve_vital_observation_context(db, obs_self)
        assert ctx.activity_state.state == AuthorityState.UNKNOWN
        assert ctx.altitude.state == AuthorityState.UNKNOWN
        assert ctx.temperature_method.state == AuthorityState.UNKNOWN
        assert ctx.quality_state.state == AuthorityState.UNKNOWN
        assert ctx.confirmation_state.state == AuthorityState.UNKNOWN
        assert ctx.confirmation_state.value == "UNCONFIRMED"
        assert ctx.symptom_refs.state == AuthorityState.KNOWN
        assert len(ctx.symptom_refs.value) == 1
        assert ctx.symptom_refs.value[0]["symptom_label"] == "shortness of breath"
        assert ctx.medication_context.state in (AuthorityState.KNOWN, AuthorityState.UNKNOWN)
        if ctx.medication_context.state == AuthorityState.KNOWN:
            assert ctx.medication_context.value["effect"] == "UNKNOWN"
            assert ctx.medication_context.value["observation_linked"] is False

        # Managed / other-subject boundary: no symptom link
        obs_other = CanonicalVitalObservation(
            metric="spo2",
            normalized_value=96.0,
            unit="percent",
            measured_at=when,
            source_class=SOURCE_CLASS_LEGACY_HEALTHDATA,
            account_user_id=user_a.id,
            health_subject_id=managed.id,
            device_id=None,
            quality_state=None,
            provenance={"health_data_id": 10, "unit_authority": "test"},
            structural_parse_ok=True,
        )
        ctx_other = resolve_vital_observation_context(db, obs_other)
        assert ctx_other.symptom_refs.state == AuthorityState.UNKNOWN
        assert ctx_other.symptom_refs.source == "symptom_subject_boundary"

        # Confirmation not inferred from multiple HealthData rows
        for i in range(3):
            db.add(
                models.HealthData(
                    user_id=user_a.id,
                    heart_rate="72",
                    created_at=when.replace(tzinfo=None) - timedelta(minutes=i),
                )
            )
        db.commit()
        ctx2 = resolve_vital_observation_context(db, obs_self)
        assert ctx2.confirmation_state.state == AuthorityState.UNKNOWN

        # Eligibility fail-closed
        result = evaluate_shadow_eligibility(db, [obs_self], attach_context=True)
        assert result.eligible is False
        assert BLOCKED_MISSING_CONTEXT in result.blockers
        assert BLOCKED_MEASUREMENT_QUALITY in result.blockers
        assert BLOCKED_CONFIRMATION in result.blockers
        assert BLOCKED_POLICY_NOT_APPROVED in result.blockers

        before = db.execute(text("SELECT COUNT(*) FROM notifications")).scalar_one()
        evaluate_shadow_eligibility(db, [obs_self])
        after = db.execute(text("SELECT COUNT(*) FROM notifications")).scalar_one()
        assert before == after

        assert db.execute(text("SELECT COUNT(*) FROM i9_absolute_vital_policies")).scalar_one() == 0
    finally:
        db.close()
        isolated.close()


def test_g11_g9_adapter_preserved_and_unknown_blocks():
    db = MagicMock()
    hd = models.HealthData(
        user_id=1,
        heart_rate="80",
        spo2="97",
        temperature="36.8",
        created_at=datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc),
    )
    hd.id = 42
    with patch(
        "backend.app.services.i9.absolute_vital_observation.resolve_self_health_subject_id",
        return_value=7,
    ):
        obs = adapt_health_data_to_observations(db, hd)
    assert len(obs) == 3
    assert all(o.structural_parse_ok for o in obs)
    assert all(o.quality_state is None for o in obs)
    assert all(o.provenance.get("healthdata_pm_dual_write") == "DEFERRED" for o in obs)

    from dataclasses import replace

    from backend.app.services.i9.vital_observation_context import (
        ContextualField,
        VitalObservationContext,
        _unknown,
    )

    def _fake_attach(_db, observations):
        out = []
        for o in observations:
            ctx = VitalObservationContext(
                activity_state=_unknown(source="test"),
                symptom_refs=_unknown(source="test"),
                altitude=_unknown(source="test"),
                temperature_method=_unknown(source="test"),
                quality_state=_unknown(source="test"),
                confirmation_state=_unknown(source="test", value="UNCONFIRMED"),
                medication_context=ContextualField(
                    state=AuthorityState.KNOWN,
                    value={
                        "inventory_refs": [{"user_medication_id": 1, "medication_id": 2}],
                        "effect": "UNKNOWN",
                        "observation_linked": False,
                        "authority": "OPTIONAL_PARTIAL",
                    },
                    source="test",
                ),
                diagnostics={"medication_effect_inferred": False},
            )
            prov = dict(o.provenance)
            prov["context_object"] = ctx
            out.append(replace(o, provenance=prov))
        return out

    with patch(
        "backend.app.services.i9.absolute_vital_shadow_eligibility.attach_context_to_observations",
        side_effect=_fake_attach,
    ):
        result = evaluate_shadow_eligibility(MagicMock(), obs, attach_context=True)
    assert result.eligible is False
    assert BLOCKED_MISSING_CONTEXT in result.blockers
    assert BLOCKED_MEASUREMENT_QUALITY in result.blockers
    assert BLOCKED_CONFIRMATION in result.blockers
    assert BLOCKED_POLICY_NOT_APPROVED in result.blockers
    elig = evaluate_observation_eligibility(result.observations[0].observation)
    assert "TACHYCARDIA" not in "".join(elig.blockers)
