"""I5-KNOW-02 — artifacts, multi-evidence, claims, universal taxonomy tests."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.i5.enums import (
    ArtifactVersionState,
    EvidenceSupportDirection,
    KnowledgeDimensionCode,
    SediCoveragePriority,
    SediRootCategory,
)
from backend.app.services.i5.know02.artifacts import link_evidence
from backend.app.services.i5.know02.eligibility import (
    claim_has_only_retracted_support,
    runtime_evidence_allowed,
    supporting_links_for_runtime,
)
from backend.app.services.i5.know02.seed_fixtures import seed_know02_foundation
from backend.app.services.i5.know02.taxonomy import query_kus_by_concept_and_dimension


def _pg_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def test_know02_no_p0_branching_in_core_services():
    root = Path("backend/app/services/i5/know02")
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                # forbid identity compares against hard-coded disease string literals in ifs is soft;
                # stronger: no `if disease == "ALS"` Assign/Compare patterns with ALS/MS alone
                pass
        src = path.read_text(encoding="utf-8")
        assert 'if disease == "ALS"' not in src
        assert "elif disease == \"MS\"" not in src
        assert "if disease == 'ALS'" not in src


def test_know02_dimension_enum_covers_care_lifestyle():
    needed = {
        "NUTRITION",
        "EXERCISE",
        "LIFESTYLE",
        "SLEEP",
        "DAILY_ROUTINE",
        "PREVENTION",
        "CARE",
        "MENTAL_HEALTH",
    }
    assert needed <= {e.value for e in KnowledgeDimensionCode}


@pytest.mark.skipif(not _pg_url(), reason="TEST_DATABASE_URL not set")
def test_know02_foundation_universality_multi_evidence_queries():
    from backend.app import models

    url = _pg_url()
    engine = create_engine(url)
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head != "063_i5_know02_artifacts_claims_taxonomy":
            pytest.skip(f"alembic head {head} != 063")
        for t in (
            "i5_scientific_artifacts",
            "i5_scientific_artifact_versions",
            "i5_knowledge_unit_evidence_links",
            "i5_clinical_concepts",
            "i5_knowledge_claim_details",
            "i5_knowledge_dimensions",
        ):
            assert conn.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name=:t"), {"t": t}
            ).scalar()

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # clean prior know02 fixture keys
        for ku in (
            db.query(models.KnowledgeUnit)
            .filter(models.KnowledgeUnit.canonical_unit_id.like("know02:%"))
            .all()
        ):
            db.delete(ku)
        for art in (
            db.query(models.I5ScientificArtifact)
            .filter(models.I5ScientificArtifact.artifact_key.like("fixture:%"))
            .all()
        ):
            db.delete(art)
        for c in (
            db.query(models.I5ClinicalConcept)
            .filter(
                (models.I5ClinicalConcept.concept_key.like("disease:%"))
                | (models.I5ClinicalConcept.concept_key.like("family:%"))
                | (models.I5ClinicalConcept.concept_key.like("population:%"))
            )
            .all()
        ):
            db.delete(c)
        db.commit()

        summary = seed_know02_foundation(db)
        db.commit()
        assert summary["p0_specific_branching_in_core_schema"] == 0
        assert summary["icd11_full_import"] == "NEXT_TERMINOLOGY_WAVE"

        # ALS/MS/Diabetes in universal taxonomy + P0 overlay
        als = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:als").one()
        ms = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:ms").one()
        dm = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:diabetes_mellitus").one()
        assert als.root_category == SediRootCategory.NERVOUS_SYSTEM.value
        assert ms.root_category == SediRootCategory.NERVOUS_SYSTEM.value
        assert dm.root_category == SediRootCategory.ENDOCRINE_NUTRITIONAL_METABOLIC.value
        overlays = db.query(models.I5SediPriorityOverlay).filter_by(active=True).all()
        assert any(o.priority_class == SediCoveragePriority.P0_CRITICAL.value for o in overlays)

        # Non-P0 diseases exist
        for key in (
            "disease:hypertension",
            "disease:influenza",
            "disease:breast_cancer",
            "disease:major_depression",
            "disease:asthma",
            "disease:ckd",
        ):
            assert db.query(models.I5ClinicalConcept).filter_by(concept_key=key).one()

        # Query: ALS + respiratory care
        als_resp = query_kus_by_concept_and_dimension(
            db, concept_id=als.id, dimension_code=KnowledgeDimensionCode.RESPIRATORY_CARE.value
        )
        assert als_resp

        # MS + exercise
        ms_ex = query_kus_by_concept_and_dimension(
            db, concept_id=ms.id, dimension_code=KnowledgeDimensionCode.EXERCISE.value
        )
        assert ms_ex

        t2 = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:diabetes:t2").one()
        t2_nut = query_kus_by_concept_and_dimension(
            db, concept_id=t2.id, dimension_code=KnowledgeDimensionCode.NUTRITION.value
        )
        assert t2_nut

        # Cross-disease claim F
        ku_f = (
            db.query(models.KnowledgeUnit)
            .filter_by(canonical_unit_id="know02:claim:f:cross_exercise")
            .one()
        )
        concepts_f = (
            db.query(models.I5KnowledgeUnitConcept).filter_by(knowledge_unit_id=ku_f.id).all()
        )
        assert len(concepts_f) >= 3

        # Healthy population claim G
        healthy = db.query(models.I5ClinicalConcept).filter_by(concept_key="population:healthy").one()
        healthy_kus = query_kus_by_concept_and_dimension(
            db, concept_id=healthy.id, dimension_code=KnowledgeDimensionCode.EXERCISE.value
        )
        assert healthy_kus

        # Multi-evidence: claim A has >=2 links; claim B has SUPPORTS + CONTRADICTS
        ku_a = (
            db.query(models.KnowledgeUnit)
            .filter_by(canonical_unit_id="know02:claim:a:als_resp")
            .one()
        )
        links_a = (
            db.query(models.I5KnowledgeUnitEvidenceLink).filter_by(knowledge_unit_id=ku_a.id).all()
        )
        assert len(links_a) >= 2

        ku_b = (
            db.query(models.KnowledgeUnit)
            .filter_by(canonical_unit_id="know02:claim:b:ms_exercise")
            .one()
        )
        dirs = {
            l.support_direction
            for l in db.query(models.I5KnowledgeUnitEvidenceLink)
            .filter_by(knowledge_unit_id=ku_b.id)
            .all()
        }
        assert EvidenceSupportDirection.SUPPORTS.value in dirs
        assert EvidenceSupportDirection.CONTRADICTS.value in dirs

        # Retracted-only cannot support runtime
        ku_d = (
            db.query(models.KnowledgeUnit)
            .filter_by(canonical_unit_id="know02:claim:d:retracted_only")
            .one()
        )
        links_d = (
            db.query(models.I5KnowledgeUnitEvidenceLink).filter_by(knowledge_unit_id=ku_d.id).all()
        )
        versions = {
            v.id: v
            for v in db.query(models.I5ScientificArtifactVersion).all()
        }
        assert claim_has_only_retracted_support(links_d, versions) is True
        assert supporting_links_for_runtime(links_d, versions) == []
        ret_v = versions[summary["retracted_version_id"]]
        assert runtime_evidence_allowed(ret_v) is False
        assert ret_v.version_state == ArtifactVersionState.RETRACTED.value

        with pytest.raises(PermissionError):
            link_evidence(
                db,
                knowledge_unit_id=ku_d.id,
                artifact_version_id=ret_v.id,
                support_direction=EvidenceSupportDirection.SUPPORTS.value,
                enforce_runtime_support=True,
            )

        # Claim details exist
        assert db.query(models.I5KnowledgeClaimDetail).count() >= 5

        # Artifact version immutability: same label returns same row
        from backend.app.services.i5.know02.artifacts import add_artifact_version

        art = db.query(models.I5ScientificArtifact).filter_by(artifact_key="fixture:rct:ms_exercise").one()
        v1 = add_artifact_version(db, artifact_id=art.id, version_label="1", content_hash="a" * 64)
        v1b = add_artifact_version(db, artifact_id=art.id, version_label="1", content_hash="b" * 64)
        assert v1.id == v1b.id

        # Source → artifact → version → evidence → KU → concept → dimension
        assert art.source_profile_id is not None
        sav = db.query(models.I5ScientificArtifactVersion).filter_by(artifact_id=art.id).first()
        link = (
            db.query(models.I5KnowledgeUnitEvidenceLink)
            .filter_by(artifact_version_id=sav.id)
            .first()
        )
        assert link is not None
        assert (
            db.query(models.I5KnowledgeUnitConcept)
            .filter_by(knowledge_unit_id=link.knowledge_unit_id)
            .count()
            >= 1
        )
        assert (
            db.query(models.I5KnowledgeUnitDimension)
            .filter_by(knowledge_unit_id=link.knowledge_unit_id)
            .count()
            >= 1
        )

        # Sleep/daily-routine
        osa = db.query(models.I5ClinicalConcept).filter_by(concept_key="disease:osa").one()
        assert query_kus_by_concept_and_dimension(
            db, concept_id=osa.id, dimension_code=KnowledgeDimensionCode.DAILY_ROUTINE.value
        )

        # Terminology releases present
        assert (
            db.query(models.I5TerminologyRelease)
            .filter_by(terminology_system="ICD11")
            .count()
            >= 1
        )
        assert (
            db.query(models.I5TerminologyRelease).filter_by(terminology_system="ICF").count() >= 1
        )
        assert (
            db.query(models.I5TerminologyRelease).filter_by(terminology_system="ICHI").count() >= 1
        )
    finally:
        db.close()
        engine.dispose()
