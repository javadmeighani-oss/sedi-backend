"""I5-S49 trusted-source control, governed eligibility, and SCIS serving bridge tests."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeUnitRuntimeEligibility,
    KnowledgeType,
    MedicalSafetyState,
    PublicationState,
    ReviewState,
)
from backend.app.services.i5.governed_low_risk_eligibility import (
    apply_governed_low_risk_fields,
    can_apply_governed_low_risk,
    connector_blocks_governed_low_risk,
    finalize_governed_runtime_eligibility,
)
from backend.app.services.i5.trusted_source_manifest import (
    MANIFEST_AUTHORITY,
    PYTHON_SEED_RUNTIME_AUTHORITY,
    active_source_keys,
    governed_low_risk_eligible,
    load_trusted_source_manifest,
    validate_manifest_contract,
)
from backend.app.services.scis.contracts import RetrievalMode, ScisRetrievalRequest
from backend.app.services.scis.retrieval import retrieve


def test_manifest_is_canonical_authority():
    data = load_trusted_source_manifest()
    assert data["manifest_authority"] == MANIFEST_AUTHORITY
    contract = validate_manifest_contract()
    assert contract["python_seed_runtime_authority"] is PYTHON_SEED_RUNTIME_AUTHORITY
    assert contract["active_count"] >= 4
    assert "nhs_uk_live_well" in active_source_keys()


def test_governed_low_risk_flags_per_source():
    assert governed_low_risk_eligible("nhs_uk_live_well") is True
    assert governed_low_risk_eligible("cdc_health_lifestyle") is True
    assert governed_low_risk_eligible("medlineplus_consumer_health") is False
    assert governed_low_risk_eligible("nimh_nih_mental_health") is False
    assert governed_low_risk_eligible("pubmed_ncbi_eutils") is False


def test_high_risk_connector_and_domain_fail_closed():
    assert connector_blocks_governed_low_risk("pubmed_ncbi_eutils") is True
    assert can_apply_governed_low_risk(
        source_key="nhs_uk_live_well",
        domain="diabetes",
        provenance_complete=True,
    ) is False
    assert can_apply_governed_low_risk(
        source_key="medlineplus_consumer_health",
        domain="lifestyle",
        provenance_complete=True,
    ) is False


def test_finalize_eligibility_low_risk_official(db):
    from backend.app import models

    ku = models.KnowledgeUnit(
        canonical_unit_id="ku-s49-test",
        immutable_version_id="v1",
        domain="lifestyle",
        topic_taxonomy="sleep",
        language="en",
        knowledge_type=KnowledgeType.OTHER.value,
        normalized_statement="Regular sleep supports wellbeing.",
        applicability="general",
        population="general",
        jurisdiction="GB",
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=MedicalSafetyState.PENDING_REVIEW.value,
        conflict_state=ConflictState.NONE.value,
        freshness_state=FreshnessState.UNKNOWN.value,
        review_state=ReviewState.NOT_REVIEWED.value,
        publication_state=PublicationState.DRAFT.value,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
        provenance_complete=True,
        deduplication_key="s49-dedupe-1",
        canonical_hash="abc",
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()

    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    assert elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value
    assert ku.medical_safety_state == MedicalSafetyState.CLEARED.value


def test_finalize_eligibility_pubmed_stays_not_eligible(db):
    from backend.app import models

    ku = models.KnowledgeUnit(
        canonical_unit_id="ku-s49-pubmed",
        immutable_version_id="v1",
        domain="neurology",
        knowledge_type=KnowledgeType.FACT.value,
        normalized_statement="Amyotrophic lateral sclerosis trial registration.",
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=MedicalSafetyState.UNKNOWN.value,
        conflict_state=ConflictState.NONE.value,
        freshness_state=FreshnessState.CURRENT.value,
        review_state=ReviewState.NOT_REVIEWED.value,
        publication_state=PublicationState.CANDIDATE.value,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
        provenance_complete=True,
        deduplication_key="s49-pubmed",
        canonical_hash="def",
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()

    elig = finalize_governed_runtime_eligibility(
        ku,
        source_key="pubmed_ncbi_eutils",
        domain="neurology",
        connector_key="pubmed_ncbi_eutils",
    )
    assert elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE


@pytest.mark.skipif(
    not __import__("os").environ.get("TEST_DATABASE_URL"),
    reason="SCIS DB integration requires TEST_DATABASE_URL",
)
def test_ku_to_kce_lexical_retrieval_with_provenance(db):
    from backend.app import models
    from backend.app.services.scis.embedding.providers import FakeScisEmbeddingProvider
    from backend.app.services.scis.serving_bridge import index_eligible_knowledge_unit_if_ready

    ku = models.KnowledgeUnit(
        canonical_unit_id="ku-s49-scis",
        immutable_version_id="v1",
        domain="lifestyle",
        topic_taxonomy="exercise",
        language="en",
        knowledge_type=KnowledgeType.OTHER.value,
        normalized_statement="NHS live well exercise guidance for healthy adults.",
        applicability="general",
        population="general",
        jurisdiction="GB",
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=MedicalSafetyState.PENDING_REVIEW.value,
        conflict_state=ConflictState.NONE.value,
        freshness_state=FreshnessState.UNKNOWN.value,
        review_state=ReviewState.NOT_REVIEWED.value,
        publication_state=PublicationState.DRAFT.value,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
        provenance_complete=True,
        deduplication_key="s49-scis",
        canonical_hash="ghi",
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()

    apply_governed_low_risk_fields(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    ku.runtime_eligibility = elig.value
    db.flush()

    rows = index_eligible_knowledge_unit_if_ready(db, ku, source_profile_id=1, raw_evidence_id=1)
    assert len(rows) >= 1

    resp = retrieve(
        db,
        ScisRetrievalRequest(
            query_text="NHS live well exercise",
            top_k=5,
            mode=RetrievalMode.LEXICAL_ONLY,
            allowed_knowledge_classes=["GLOBAL_GOVERNED_KNOWLEDGE"],
        ),
        provider=FakeScisEmbeddingProvider(),
    )
    assert resp.fallback_state.value in {"NONE", "no_eligible_knowledge"}
    if resp.evidence_items:
        item = resp.evidence_items[0]
        assert item.provenance.knowledge_unit_id == int(ku.id)
        assert item.provenance.chunk_id is not None
