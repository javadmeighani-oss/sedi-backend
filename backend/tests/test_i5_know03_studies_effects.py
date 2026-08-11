"""I5-KNOW-03 — W0 integrity + studies/PICO/effects/recommendations tests."""

from __future__ import annotations

import ast
import math
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.services.i5.enums import (
    EffectMeasure,
    RecommendationStatus,
    StudyDesign,
)
from backend.app.services.i5.know02.artifacts import ContentDriftConflict, add_artifact_version, upsert_artifact
from backend.app.services.i5.know02.eligibility import runtime_evidence_allowed
from backend.app.services.i5.know03.effects import add_effect_estimate
from backend.app.services.i5.know03.seed_fixtures import seed_know03_foundation
from backend.app.services.i5.know03.validation import EffectValidationError, validate_effect_payload


def _pg_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def test_know03_no_p0_branching_in_core_services():
    root = Path("backend/app/services/i5/know03")
    for path in root.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert 'if disease == "ALS"' not in src
        assert "elif disease == \"MS\"" not in src
        assert ast.parse(src, filename=str(path)) is not None


def test_know03_effect_validation_rejects_nan_inf_bad_ci():
    with pytest.raises(EffectValidationError):
        validate_effect_payload(effect_value=float("nan"))
    with pytest.raises(EffectValidationError):
        validate_effect_payload(effect_value=float("inf"))
    with pytest.raises(EffectValidationError):
        validate_effect_payload(ci_lower=2.0, ci_upper=1.0)
    with pytest.raises(EffectValidationError):
        validate_effect_payload(confidence_level=0)
    with pytest.raises(EffectValidationError):
        validate_effect_payload(sample_size_analyzed=-1)
    with pytest.raises(EffectValidationError):
        validate_effect_payload(sample_size_analyzed=10, event_count_intervention=11)
    ok = validate_effect_payload(effect_value=1.2, ci_lower=1.0, ci_upper=1.5, confidence_level=95)
    assert ok["effect_value"] == 1.2
    assert not math.isnan(ok["effect_value"])


@pytest.mark.skipif(not _pg_url(), reason="TEST_DATABASE_URL not set")
def test_know03_w0_and_studies_foundation():
    from backend.app import models

    url = _pg_url()
    engine = create_engine(url)
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head != "064_i5_know03_studies_effects_recs" and head != "065_i5_know04_connectors_change_intelligence":
            pytest.skip(f"alembic head {head} not in {{064,065}}")
        for t in (
            "i5_clinical_studies",
            "i5_study_populations",
            "i5_study_effect_estimates",
            "i5_clinical_recommendations",
            "i5_artifact_version_content_drift_events",
            "i5_terminology_import_contracts",
        ):
            assert conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name=:t"), {"t": t}
            ).scalar()
        assert conn.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name='user_clinical_feature_index'")
        ).scalar() is None

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        summary = seed_know03_foundation(db)
        db.commit()
        assert summary["p0_specific_branching_in_core_study_model"] == 0
        assert summary["silent_content_drift"] == 0
        assert summary["icd11_full_import"] == "NEXT_TERMINOLOGY_WAVE"

        # W0 NF5
        art = upsert_artifact(
            db, artifact_key="fixture:know03:drift_probe", artifact_type="ARTICLE", title="drift"
        )
        db.flush()
        v = add_artifact_version(db, artifact_id=art.id, version_label="1", content_hash="aa" * 32)
        assert add_artifact_version(db, artifact_id=art.id, version_label="1", content_hash="aa" * 32).id == v.id
        with pytest.raises(ContentDriftConflict):
            add_artifact_version(db, artifact_id=art.id, version_label="1", content_hash="bb" * 32)
        db.commit()
        assert db.query(models.I5ArtifactVersionContentDriftEvent).filter_by(artifact_id=art.id).count() >= 1

        # W0 NF6 nullable uniqueness
        als = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:als").one()
        db.add(
            models.I5ClinicalConceptMapping(
                concept_id=als.id,
                terminology_system="MESH",
                external_code="FIX-NULL-UQ-KNOW03",
                release_version=None,
            )
        )
        db.flush()
        db.add(
            models.I5ClinicalConceptMapping(
                concept_id=als.id,
                terminology_system="MESH",
                external_code="FIX-NULL-UQ-KNOW03",
                release_version=None,
            )
        )
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

        # Orphan / cross-artifact supersession
        art2 = upsert_artifact(db, artifact_key="fixture:know03:sup_probe", artifact_type="ARTICLE")
        db.flush()
        with pytest.raises(ValueError, match="ORPHAN_SUPERSESSION"):
            add_artifact_version(
                db, artifact_id=art2.id, version_label="1", content_hash="cc" * 32, supersedes_version_id=999999999
            )
        a1 = upsert_artifact(db, artifact_key="fixture:know03:cross_a", artifact_type="ARTICLE")
        a2 = upsert_artifact(db, artifact_key="fixture:know03:cross_b", artifact_type="ARTICLE")
        db.flush()
        v_a = add_artifact_version(db, artifact_id=a1.id, version_label="1", content_hash="dd" * 32)
        with pytest.raises(ValueError, match="CROSS_ARTIFACT_SUPERSESSION"):
            add_artifact_version(
                db,
                artifact_id=a2.id,
                version_label="1",
                content_hash="ee" * 32,
                supersedes_version_id=v_a.id,
            )
        db.rollback()

        # Re-load seeded foundation rows (still committed from first seed)
        als_study = db.query(models.I5ClinicalStudy).filter_by(study_key="study:know03:als_resp").one()
        assert als_study.study_design == StudyDesign.RANDOMIZED_CONTROLLED_TRIAL.value
        assert db.query(models.I5StudyPopulation).filter_by(study_id=als_study.id).count() >= 1
        assert db.query(models.I5StudyPopulationCriterion).count() >= 1
        assert db.query(models.I5StudyIntervention).filter_by(study_id=als_study.id).count() >= 2
        assert db.query(models.I5StudyOutcome).filter_by(study_id=als_study.id, is_harm=True).count() >= 1
        effects = db.query(models.I5StudyEffectEstimate).filter_by(study_id=als_study.id).all()
        assert any(e.effect_measure == EffectMeasure.MEAN_DIFFERENCE.value for e in effects)
        assert any(e.effect_measure == EffectMeasure.RISK_RATIO.value for e in effects)
        assert any(e.statistical_significance and e.clinical_significance for e in effects)

        so = db.query(models.I5StudyOutcome).filter_by(study_id=als_study.id).first()
        with pytest.raises(EffectValidationError):
            add_effect_estimate(
                db,
                study_id=als_study.id,
                study_outcome_id=so.id,
                effect_measure=EffectMeasure.HAZARD_RATIO.value,
                ci_lower=2.0,
                ci_upper=1.0,
            )
        db.rollback()

        rec1 = db.query(models.I5ClinicalRecommendation).filter_by(recommendation_key="rec:als:resp:v1").one()
        rec2 = db.query(models.I5ClinicalRecommendation).filter_by(recommendation_key="rec:als:resp:v2").one()
        assert rec1.status == RecommendationStatus.SUPERSEDED.value
        assert rec1.superseded_by_id == rec2.id
        assert rec2.status == RecommendationStatus.CURRENT.value
        assert db.query(models.I5ClinicalRecommendation).filter_by(
            recommendation_key="rec:ms:exercise:conditional"
        ).one()
        assert db.query(models.I5ClinicalRecommendation).filter_by(
            recommendation_key="rec:ms:exercise:against_unsupervised"
        ).one()

        ret_v = (
            db.query(models.I5ScientificArtifactVersion)
            .join(models.I5ScientificArtifact)
            .filter(models.I5ScientificArtifact.artifact_key == "fixture:know03:retracted_primary")
            .one()
        )
        assert runtime_evidence_allowed(ret_v) is False
        assert db.query(models.I5ClinicalStudy).filter_by(study_key="study:know03:retracted").one()

        assert db.query(models.I5TerminologyImportContract).filter_by(terminology_system="ICD11").count() >= 1
        assert db.query(models.I5TerminologyImportContract).filter_by(terminology_system="RXNORM").count() >= 1
        assert db.query(models.I5TerminologyImportContract).filter_by(terminology_system="LOINC").count() >= 1
        assert (
            db.query(models.I5ClinicalStudy)
            .filter(models.I5ClinicalStudy.study_key.like("study:know03:%"))
            .count()
            >= 10
        )
        assert db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:osteoarthritis").one()
    finally:
        db.close()
        engine.dispose()
