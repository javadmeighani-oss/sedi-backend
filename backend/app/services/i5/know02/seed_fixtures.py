"""KNOW-02 synthetic foundation seed — universality + P0 overlay + multi-evidence scenarios."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    ArtifactType,
    ArtifactVersionState,
    ClaimClass,
    ClinicalConceptType,
    CoverageCellState,
    EvidenceSupportDirection,
    KnowledgeDimensionCode,
    SediCoveragePriority,
    SediRootCategory,
    TerminologySystem,
)
from backend.app.services.i5.know02.artifacts import (
    add_artifact_version,
    link_evidence,
    mark_version_state,
    upsert_artifact,
    upsert_claim_detail,
)
from backend.app.services.i5.know02.taxonomy import (
    add_label,
    add_mapping,
    link_ku_concept,
    link_ku_dimension,
    seed_all_dimensions,
    set_priority_overlay,
    upsert_concept,
    upsert_coverage_cell,
)


def _sha(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def _ensure_gsp(db: Session, key: str) -> models.GovernedSourceProfile:
    row = db.query(models.GovernedSourceProfile).filter_by(canonical_key=key).first()
    if row:
        return row
    row = models.GovernedSourceProfile(
        canonical_key=key,
        operational_status="disabled",
        registry_state="DISCOVERED",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    db.add(row)
    db.flush()
    return row


def _make_ku(
    db: Session,
    *,
    canonical: str,
    statement: str,
    domain: str,
    knowledge_type: str = "GUIDELINE",
) -> models.KnowledgeUnit:
    from backend.app.services.i5.enums import KnowledgeType as KT

    kt = knowledge_type if knowledge_type in {e.value for e in KT} else KT.GUIDELINE.value
    digest = _sha(canonical, statement)
    existing = (
        db.query(models.KnowledgeUnit)
        .filter_by(canonical_unit_id=canonical, immutable_version_id="v1")
        .first()
    )
    if existing:
        return existing
    ku = models.KnowledgeUnit(
        canonical_unit_id=canonical,
        immutable_version_id="v1",
        domain=domain,
        language="en",
        knowledge_type=kt,
        normalized_statement=statement,
        evidence_strength="MODERATE",
        medical_safety_state="CLEARED",
        conflict_state="NONE",
        freshness_state="CURRENT",
        review_state="APPROVED",
        publication_state="PUBLISHED",
        runtime_eligibility="NOT_ELIGIBLE",
        provenance_complete=False,
        deduplication_key=digest,
        canonical_hash=digest,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()
    return ku


def seed_know02_foundation(db: Session) -> Dict[str, Any]:
    """Seed taxonomy + claim fixtures. No live terminology bulk import."""
    dim_count = seed_all_dimensions(db)

    # Terminology release metadata (ICD-11 full import = NEXT_TERMINOLOGY_WAVE)
    if not db.query(models.I5TerminologyRelease).filter_by(
        terminology_system=TerminologySystem.ICD11.value, release_version="2025-01"
    ).first():
        db.add(
            models.I5TerminologyRelease(
                terminology_system=TerminologySystem.ICD11.value,
                release_version="2025-01",
                status="ACTIVE",
                official_source_note="WHO ICD-11 API/import contract foundation",
                rights_note="ICD11_FULL_IMPORT=NEXT_TERMINOLOGY_WAVE; no proprietary bulk copy",
            )
        )
    if not db.query(models.I5TerminologyRelease).filter_by(
        terminology_system=TerminologySystem.MESH.value, release_version="2025"
    ).first():
        db.add(
            models.I5TerminologyRelease(
                terminology_system=TerminologySystem.MESH.value,
                release_version="2025",
                status="ACTIVE",
                official_source_note="NLM MeSH mapping foundation",
                rights_note="No bulk MeSH content copied in KNOW-02",
            )
        )
    for sys, ver, note in (
        (TerminologySystem.ICF.value, "2024", "ICF-compatible mapping foundation"),
        (TerminologySystem.ICHI.value, "2024", "ICHI-compatible mapping foundation"),
    ):
        if not db.query(models.I5TerminologyRelease).filter_by(
            terminology_system=sys, release_version=ver
        ).first():
            db.add(
                models.I5TerminologyRelease(
                    terminology_system=sys,
                    release_version=ver,
                    status="ACTIVE",
                    official_source_note=note,
                    rights_note="Schema/API contract only; no full ingestion",
                )
            )

    # --- Universal disease concepts (P0 + non-P0) ---
    nervous = upsert_concept(
        db,
        concept_key="family:nervous_system",
        preferred_name="Nervous system disorders",
        concept_type=ClinicalConceptType.DISEASE_FAMILY.value,
        root_category=SediRootCategory.NERVOUS_SYSTEM.value,
    )
    als = upsert_concept(
        db,
        concept_key="disease:als",
        preferred_name="Amyotrophic lateral sclerosis",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.NERVOUS_SYSTEM.value,
        parent_concept_id=nervous.id,
        rare_disease_flag=True,
        adult_relevance=True,
    )
    add_mapping(
        db,
        concept_id=als.id,
        terminology_system=TerminologySystem.ICD11.value,
        external_code="8B60.0",
        release_version="2025-01",
        is_primary=True,
        mapping_status="PROVISIONAL",
        provenance_note="FACT: placeholder ICD-11-compatible code slot; REVIEW_REQUIRED against official release",
    )
    add_label(db, concept_id=als.id, language="en", label_kind="ABBREVIATION", label_text="ALS", verified=True)
    add_label(
        db,
        concept_id=als.id,
        language="fa",
        label_kind="COMMON_NAME",
        label_text="اسکلروز جانبی آمیوتروفیک",
        verified=False,
        provenance_note="UNVERIFIED patient-language seed; not auto-canonical",
    )
    set_priority_overlay(
        db,
        concept_id=als.id,
        priority_class=SediCoveragePriority.P0_CRITICAL.value,
        track_key="ALS",
        rationale="P0 overlay — taxonomy identity unchanged",
    )

    ms = upsert_concept(
        db,
        concept_key="disease:ms",
        preferred_name="Multiple sclerosis",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.NERVOUS_SYSTEM.value,
        parent_concept_id=nervous.id,
        adult_relevance=True,
    )
    add_mapping(
        db,
        concept_id=ms.id,
        terminology_system=TerminologySystem.ICD11.value,
        external_code="8A40",
        release_version="2025-01",
        is_primary=True,
        mapping_status="PROVISIONAL",
        provenance_note="PROVISIONAL ICD-11 family code slot",
    )
    for subtype, key in (("RRMS", "disease:ms:rrms"), ("SPMS", "disease:ms:spms"), ("PPMS", "disease:ms:ppms")):
        upsert_concept(
            db,
            concept_key=key,
            preferred_name=f"Multiple sclerosis — {subtype}",
            concept_type=ClinicalConceptType.SUBTYPE.value,
            root_category=SediRootCategory.NERVOUS_SYSTEM.value,
            parent_concept_id=ms.id,
        )
    set_priority_overlay(
        db,
        concept_id=ms.id,
        priority_class=SediCoveragePriority.P0_CRITICAL.value,
        track_key="MS",
        rationale="P0 overlay",
    )

    endocrine = upsert_concept(
        db,
        concept_key="family:endocrine_metabolic",
        preferred_name="Endocrine / nutritional / metabolic disorders",
        concept_type=ClinicalConceptType.DISEASE_FAMILY.value,
        root_category=SediRootCategory.ENDOCRINE_NUTRITIONAL_METABOLIC.value,
    )
    dm = upsert_concept(
        db,
        concept_key="disease:diabetes_mellitus",
        preferred_name="Diabetes mellitus",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.ENDOCRINE_NUTRITIONAL_METABOLIC.value,
        parent_concept_id=endocrine.id,
        chronic_flag=None,  # require provenance — not guessed
    )
    t1 = upsert_concept(
        db,
        concept_key="disease:diabetes:t1",
        preferred_name="Type 1 diabetes mellitus",
        concept_type=ClinicalConceptType.SUBTYPE.value,
        root_category=SediRootCategory.ENDOCRINE_NUTRITIONAL_METABOLIC.value,
        parent_concept_id=dm.id,
    )
    t2 = upsert_concept(
        db,
        concept_key="disease:diabetes:t2",
        preferred_name="Type 2 diabetes mellitus",
        concept_type=ClinicalConceptType.SUBTYPE.value,
        root_category=SediRootCategory.ENDOCRINE_NUTRITIONAL_METABOLIC.value,
        parent_concept_id=dm.id,
    )
    for key, name in (
        ("disease:diabetes:gestational", "Gestational diabetes mellitus"),
        ("disease:diabetes:secondary", "Secondary diabetes mellitus"),
    ):
        upsert_concept(
            db,
            concept_key=key,
            preferred_name=name,
            concept_type=ClinicalConceptType.SUBTYPE.value,
            root_category=SediRootCategory.ENDOCRINE_NUTRITIONAL_METABOLIC.value,
            parent_concept_id=dm.id,
        )
    set_priority_overlay(
        db,
        concept_id=dm.id,
        priority_class=SediCoveragePriority.P0_CRITICAL.value,
        track_key="DIABETES",
        rationale="P0 overlay on diabetes mellitus parent",
    )
    set_priority_overlay(
        db,
        concept_id=t2.id,
        priority_class=SediCoveragePriority.P0_CRITICAL.value,
        track_key="DIABETES_T2",
        rationale="P0 subtype overlay",
    )

    # Non-P0 universality samples
    cvd = upsert_concept(
        db,
        concept_key="disease:hypertension",
        preferred_name="Essential hypertension",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.CIRCULATORY_CARDIOVASCULAR.value,
    )
    influenza = upsert_concept(
        db,
        concept_key="disease:influenza",
        preferred_name="Influenza",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.INFECTIOUS_PARASITIC.value,
        communicable_flag=None,
    )
    breast_ca = upsert_concept(
        db,
        concept_key="disease:breast_cancer",
        preferred_name="Malignant neoplasm of breast",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.NEOPLASMS_CANCER.value,
    )
    depression = upsert_concept(
        db,
        concept_key="disease:major_depression",
        preferred_name="Single episode depressive disorder",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.MENTAL_BEHAVIORAL_NEURODEVELOPMENTAL.value,
    )
    asthma = upsert_concept(
        db,
        concept_key="disease:asthma",
        preferred_name="Asthma",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.RESPIRATORY.value,
    )
    ckd = upsert_concept(
        db,
        concept_key="disease:ckd",
        preferred_name="Chronic kidney disease",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.GENITOURINARY.value,
    )
    sleep_apnea = upsert_concept(
        db,
        concept_key="disease:osa",
        preferred_name="Obstructive sleep apnoea",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.SLEEP_WAKE.value,
    )
    healthy = upsert_concept(
        db,
        concept_key="population:healthy",
        preferred_name="Healthy population",
        concept_type=ClinicalConceptType.HEALTHY_POPULATION.value,
        root_category=SediRootCategory.HEALTHY_POPULATION.value,
    )
    obesity = upsert_concept(
        db,
        concept_key="disease:obesity",
        preferred_name="Obesity",
        concept_type=ClinicalConceptType.DISEASE.value,
        root_category=SediRootCategory.ENDOCRINE_NUTRITIONAL_METABOLIC.value,
    )

    gsp = _ensure_gsp(db, "know02:fixture_publisher")

    # Artifacts
    guide = upsert_artifact(
        db,
        artifact_key="fixture:guideline:als_resp_v1",
        artifact_type=ArtifactType.GUIDELINE.value,
        title="ALS respiratory care guideline (fixture)",
        source_profile_id=gsp.id,
        guideline_id="FIX-ALS-RESP-001",
        doi="10.fixture/als.resp.guideline",
    )
    guide_v1 = add_artifact_version(
        db, artifact_id=guide.id, version_label="2024.1", content_hash=_sha("guide", "v1")
    )
    guide_v2 = add_artifact_version(
        db,
        artifact_id=guide.id,
        version_label="2025.1",
        content_hash=_sha("guide", "v2"),
        supersedes_version_id=guide_v1.id,
    )
    mark_version_state(db, version_id=guide_v1.id, version_state=ArtifactVersionState.SUPERSEDED.value)

    rct = upsert_artifact(
        db,
        artifact_key="fixture:rct:ms_exercise",
        artifact_type=ArtifactType.RCT.value,
        title="MS exercise RCT (fixture)",
        source_profile_id=gsp.id,
        pmid="9990001",
        doi="10.fixture/ms.exercise.rct",
    )
    rct_v = add_artifact_version(db, artifact_id=rct.id, version_label="1", content_hash=_sha("rct"))

    sr = upsert_artifact(
        db,
        artifact_key="fixture:sr:ms_exercise_contra",
        artifact_type=ArtifactType.SYSTEMATIC_REVIEW.value,
        title="MS exercise systematic review contradicting (fixture)",
        source_profile_id=gsp.id,
        pmid="9990002",
    )
    sr_v = add_artifact_version(db, artifact_id=sr.id, version_label="1", content_hash=_sha("sr"))

    obs = upsert_artifact(
        db,
        artifact_key="fixture:obs:t2dm_nutrition",
        artifact_type=ArtifactType.OBSERVATIONAL_STUDY.value,
        title="T2DM nutrition observational (fixture)",
        source_profile_id=gsp.id,
        pmid="9990003",
    )
    obs_v = add_artifact_version(db, artifact_id=obs.id, version_label="1", content_hash=_sha("obs"))

    retracted = upsert_artifact(
        db,
        artifact_key="fixture:article:retracted",
        artifact_type=ArtifactType.ARTICLE.value,
        title="Retracted article (fixture)",
        source_profile_id=gsp.id,
        pmid="9990004",
        doi="10.fixture/retracted",
    )
    ret_v = add_artifact_version(
        db, artifact_id=retracted.id, version_label="1", content_hash=_sha("ret")
    )
    mark_version_state(db, version_id=ret_v.id, version_state=ArtifactVersionState.RETRACTED.value)

    cross = upsert_artifact(
        db,
        artifact_key="fixture:guideline:exercise_cross",
        artifact_type=ArtifactType.GUIDELINE.value,
        title="Cross-disease exercise guideline (fixture)",
        source_profile_id=gsp.id,
        guideline_id="FIX-EXERCISE-CROSS",
    )
    cross_v = add_artifact_version(db, artifact_id=cross.id, version_label="1", content_hash=_sha("cross"))

    prev = upsert_artifact(
        db,
        artifact_key="fixture:guideline:healthy_prevention",
        artifact_type=ArtifactType.GUIDELINE.value,
        title="Healthy population physical activity (fixture)",
        source_profile_id=gsp.id,
        guideline_id="FIX-HEALTHY-PA",
    )
    prev_v = add_artifact_version(db, artifact_id=prev.id, version_label="1", content_hash=_sha("prev"))

    # CLAIM A — ALS respiratory care, guideline + multi-version same artifact
    ku_a = _make_ku(
        db,
        canonical="know02:claim:a:als_resp",
        statement="ALS respiratory care requires governed monitoring of ventilatory support needs.",
        domain="neurology",
    )
    link_ku_concept(db, knowledge_unit_id=ku_a.id, concept_id=als.id)
    link_ku_dimension(db, knowledge_unit_id=ku_a.id, dimension_code=KnowledgeDimensionCode.RESPIRATORY_CARE.value)
    link_ku_dimension(db, knowledge_unit_id=ku_a.id, dimension_code=KnowledgeDimensionCode.CARE.value)
    upsert_claim_detail(
        db,
        knowledge_unit_id=ku_a.id,
        claim_class=ClaimClass.CARE_RELATION.value,
        subject_concept_id=als.id,
        predicate="requires_monitoring",
        population_context="adults with ALS",
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_a.id,
        artifact_version_id=guide_v2.id,
        support_direction=EvidenceSupportDirection.SUPPORTS.value,
        evidence_role="PRIMARY_GUIDELINE",
        enforce_runtime_support=True,
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_a.id,
        artifact_version_id=guide_v1.id,
        support_direction=EvidenceSupportDirection.WEAKLY_SUPPORTS.value,
        evidence_role="PRIOR_VERSION",
    )

    # CLAIM B — MS exercise, RCT supports + SR contradicts
    ku_b = _make_ku(
        db,
        canonical="know02:claim:b:ms_exercise",
        statement="Structured exercise may improve function in MS (fixture contested claim).",
        domain="neurology",
    )
    link_ku_concept(db, knowledge_unit_id=ku_b.id, concept_id=ms.id)
    link_ku_dimension(db, knowledge_unit_id=ku_b.id, dimension_code=KnowledgeDimensionCode.EXERCISE.value)
    upsert_claim_detail(
        db,
        knowledge_unit_id=ku_b.id,
        claim_class=ClaimClass.EXERCISE_RELATION.value,
        subject_concept_id=ms.id,
        intervention_text="structured exercise",
        outcome_text="function",
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_b.id,
        artifact_version_id=rct_v.id,
        support_direction=EvidenceSupportDirection.SUPPORTS.value,
        enforce_runtime_support=True,
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_b.id,
        artifact_version_id=sr_v.id,
        support_direction=EvidenceSupportDirection.CONTRADICTS.value,
    )

    # CLAIM C — T2DM nutrition single observational
    ku_c = _make_ku(
        db,
        canonical="know02:claim:c:t2dm_nutrition",
        statement="Dietary pattern association with glycemic outcomes in type 2 diabetes (fixture).",
        domain="endocrinology",
    )
    link_ku_concept(db, knowledge_unit_id=ku_c.id, concept_id=t2.id)
    link_ku_dimension(db, knowledge_unit_id=ku_c.id, dimension_code=KnowledgeDimensionCode.NUTRITION.value)
    upsert_claim_detail(
        db,
        knowledge_unit_id=ku_c.id,
        claim_class=ClaimClass.NUTRITION_RELATION.value,
        subject_concept_id=t2.id,
        certainty_note="LOW_OBSERVATIONAL",
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_c.id,
        artifact_version_id=obs_v.id,
        support_direction=EvidenceSupportDirection.WEAKLY_SUPPORTS.value,
        enforce_runtime_support=True,
    )

    # CLAIM D — retracted-only support (link stored historically; runtime filter must deny)
    ku_d = _make_ku(
        db,
        canonical="know02:claim:d:retracted_only",
        statement="Claim supported only by retracted artifact (fixture).",
        domain="general",
    )
    link_ku_concept(db, knowledge_unit_id=ku_d.id, concept_id=depression.id)
    link_ku_dimension(db, knowledge_unit_id=ku_d.id, dimension_code=KnowledgeDimensionCode.MENTAL_HEALTH.value)
    upsert_claim_detail(
        db,
        knowledge_unit_id=ku_d.id,
        claim_class=ClaimClass.SCIENTIFIC_FINDING.value,
        subject_concept_id=depression.id,
    )
    # store without enforce — historical link may exist; eligibility layer blocks runtime support
    link_evidence(
        db,
        knowledge_unit_id=ku_d.id,
        artifact_version_id=ret_v.id,
        support_direction=EvidenceSupportDirection.SUPPORTS.value,
        enforce_runtime_support=False,
    )

    # CLAIM E covered by multi-version on CLAIM A (same artifact versions)

    # CLAIM F — cross-disease exercise
    ku_f = _make_ku(
        db,
        canonical="know02:claim:f:cross_exercise",
        statement="Physical activity guidance applicable across diabetes, obesity, and hypertension (fixture).",
        domain="prevention",
    )
    for cid in (t2.id, obesity.id, cvd.id):
        link_ku_concept(db, knowledge_unit_id=ku_f.id, concept_id=cid)
    link_ku_dimension(db, knowledge_unit_id=ku_f.id, dimension_code=KnowledgeDimensionCode.PHYSICAL_ACTIVITY.value)
    link_ku_dimension(db, knowledge_unit_id=ku_f.id, dimension_code=KnowledgeDimensionCode.PREVENTION.value)
    upsert_claim_detail(
        db,
        knowledge_unit_id=ku_f.id,
        claim_class=ClaimClass.PREVENTION_RELATION.value,
        population_context="adults with cardiometabolic risk",
        intervention_text="physical activity",
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_f.id,
        artifact_version_id=cross_v.id,
        support_direction=EvidenceSupportDirection.SUPPORTS.value,
        enforce_runtime_support=True,
    )

    # CLAIM G — healthy population
    ku_g = _make_ku(
        db,
        canonical="know02:claim:g:healthy_pa",
        statement="Adults in the general healthy population benefit from regular physical activity (fixture).",
        domain="prevention",
    )
    link_ku_concept(db, knowledge_unit_id=ku_g.id, concept_id=healthy.id)
    link_ku_dimension(db, knowledge_unit_id=ku_g.id, dimension_code=KnowledgeDimensionCode.EXERCISE.value)
    link_ku_dimension(db, knowledge_unit_id=ku_g.id, dimension_code=KnowledgeDimensionCode.PREVENTION.value)
    upsert_claim_detail(
        db,
        knowledge_unit_id=ku_g.id,
        claim_class=ClaimClass.PREVENTION_RELATION.value,
        subject_concept_id=healthy.id,
        population_context="healthy adults",
    )
    link_evidence(
        db,
        knowledge_unit_id=ku_g.id,
        artifact_version_id=prev_v.id,
        support_direction=EvidenceSupportDirection.SUPPORTS.value,
        enforce_runtime_support=True,
    )

    # Sleep routine dimension on OSA
    ku_sleep = _make_ku(
        db,
        canonical="know02:claim:osa_routine",
        statement="Daily sleep routine consistency is relevant in obstructive sleep apnoea care (fixture).",
        domain="sleep",
    )
    link_ku_concept(db, knowledge_unit_id=ku_sleep.id, concept_id=sleep_apnea.id)
    link_ku_dimension(db, knowledge_unit_id=ku_sleep.id, dimension_code=KnowledgeDimensionCode.DAILY_ROUTINE.value)
    link_ku_dimension(db, knowledge_unit_id=ku_sleep.id, dimension_code=KnowledgeDimensionCode.SLEEP.value)
    upsert_claim_detail(
        db,
        knowledge_unit_id=ku_sleep.id,
        claim_class=ClaimClass.ROUTINE_RELATION.value,
        subject_concept_id=sleep_apnea.id,
    )

    # Multi-dimension ALS links (care/lifestyle/nutrition/exercise/prevention/mental)
    for dim in (
        KnowledgeDimensionCode.NUTRITION,
        KnowledgeDimensionCode.EXERCISE,
        KnowledgeDimensionCode.LIFESTYLE,
        KnowledgeDimensionCode.MENTAL_HEALTH,
        KnowledgeDimensionCode.PREVENTION,
        KnowledgeDimensionCode.SUPPORTIVE_CARE,
    ):
        upsert_coverage_cell(
            db,
            concept_id=als.id,
            dimension_code=dim.value,
            cell_state=CoverageCellState.PARTIAL.value,
            evidence_class="FOUNDATION",
            detail="KNOW-02 foundation cell",
        )

    db.flush()
    return {
        "dimensions": dim_count,
        "concepts": {
            "als": als.id,
            "ms": ms.id,
            "dm": dm.id,
            "t1": t1.id,
            "t2": t2.id,
            "healthy": healthy.id,
            "cvd": cvd.id,
            "influenza": influenza.id,
            "breast_ca": breast_ca.id,
            "depression": depression.id,
            "asthma": asthma.id,
            "ckd": ckd.id,
            "osa": sleep_apnea.id,
        },
        "claims": {
            "A": ku_a.id,
            "B": ku_b.id,
            "C": ku_c.id,
            "D": ku_d.id,
            "F": ku_f.id,
            "G": ku_g.id,
        },
        "retracted_version_id": ret_v.id,
        "icd11_full_import": "NEXT_TERMINOLOGY_WAVE",
        "p0_specific_branching_in_core_schema": 0,
    }
