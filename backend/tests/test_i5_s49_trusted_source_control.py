"""I5-S49 trusted-source control, governed eligibility, and lexical-only serving tests."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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
    domain_is_recognized_low_risk,
    finalize_governed_runtime_eligibility,
    normalize_eligibility_domain,
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
from backend.app.services.scis.lexical_indexing import LEXICAL_ONLY_BACKEND_KIND, LEXICAL_ONLY_MODEL_ID
from backend.app.services.scis.retrieval import retrieve


def _db_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture()
def db():
    """Local DB fixture for workflows running pytest with --noconftest."""
    url = _db_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _canonical_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _seed_lineage_fixtures(
    db,
    *,
    suffix: str | None = None,
    canonical_key: str | None = None,
) -> tuple[int, int]:
    from backend.app import models

    token = suffix or uuid.uuid4().hex
    gsp_key = canonical_key or f"s49-gsp-{_canonical_hash(token)[:24]}"
    existing_gsp = (
        db.query(models.GovernedSourceProfile).filter_by(canonical_key=gsp_key).one_or_none()
        if canonical_key
        else None
    )
    if existing_gsp is not None:
        gsp = existing_gsp
    else:
        gsp = models.GovernedSourceProfile(
            canonical_key=gsp_key,
            operational_status="ACTIVE",
            registry_state="ACTIVE",
            runtime_eligibility="ELIGIBLE",
            canonicalization_version="v1",
        )
        db.add(gsp)
        db.flush()
    raw = models.I5RawEvidence(
        source_profile_id=gsp.id,
        retrieval_timestamp=datetime.utcnow(),
        canonical_url=f"https://www.nhs.uk/live-well/exercise/{token}/",
        content_hash=_canonical_hash(f"raw-evidence-{token}"),
        hash_algorithm="SHA-256",
        storage_mode="NONE",
        retention_mode="RAW_MINIMAL_EVIDENCE_ONLY",
        rights_terms_state="UNKNOWN",
        robots_access_state="UNKNOWN",
        redaction_state="NONE",
        prohibited_data_state="UNKNOWN",
        expiry_state="ACTIVE",
    )
    db.add(raw)
    db.flush()
    return int(gsp.id), int(raw.id)


def _link_ku_provenance(db, ku, *, source_profile_id: int, raw_evidence_id: int):
    from backend.app import models

    prov = models.KnowledgeProvenance(
        knowledge_unit_id=ku.id,
        source_profile_id=source_profile_id,
        raw_evidence_id=raw_evidence_id,
        retrieval_method="TEST_FIXTURE",
        access_route="TEST",
        content_hash=_canonical_hash(f"prov-{ku.id}"),
    )
    db.add(prov)
    db.flush()
    return prov


def _kce_count(db, ku_id: int) -> int:
    from backend.app import models

    return (
        db.query(models.KnowledgeChunkEmbedding)
        .filter(models.KnowledgeChunkEmbedding.knowledge_unit_id == int(ku_id))
        .count()
    )


def _apply_existing_ku_path(db, ku, *, source_key: str, gsp_id: int, raw_id: int, prov):
    from backend.app.services.i5.governed_ku_serving import apply_governed_finalize_and_lexical_index

    with patch.object(db, "commit", db.flush):
        return apply_governed_finalize_and_lexical_index(
            db,
            ku,
            source_key=source_key,
            source_profile_id=gsp_id,
            raw_evidence_id=raw_id,
            authoritative_provenance=prov,
            incoming_source_profile_id=gsp_id,
        )


def _make_ku(db, *, domain: str, dedupe_key: str):
    from backend.app import models

    ku = models.KnowledgeUnit(
        canonical_unit_id=f"ku-{dedupe_key}",
        immutable_version_id="v1",
        domain=domain,
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
        deduplication_key=_canonical_hash(dedupe_key),
        canonical_hash=_canonical_hash(dedupe_key),
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()
    return ku


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


def test_domain_fail_closed_normalization():
    assert normalize_eligibility_domain(None) is None
    assert normalize_eligibility_domain("") is None
    assert normalize_eligibility_domain("  ") is None
    assert normalize_eligibility_domain("UNKNOWN") is None
    assert normalize_eligibility_domain("lifestyle") == "lifestyle"
    assert domain_is_recognized_low_risk("lifestyle") is True
    assert domain_is_recognized_low_risk("diabetes") is False


def test_high_risk_connector_and_domain_fail_closed():
    assert connector_blocks_governed_low_risk("pubmed_ncbi_eutils") is True
    assert can_apply_governed_low_risk(
        source_key="nhs_uk_live_well",
        domain="diabetes",
        provenance_complete=True,
    ) is False
    assert can_apply_governed_low_risk(
        source_key="nhs_uk_live_well",
        domain=None,
        provenance_complete=True,
    ) is False
    assert can_apply_governed_low_risk(
        source_key="nhs_uk_live_well",
        domain="",
        provenance_complete=True,
    ) is False
    assert can_apply_governed_low_risk(
        source_key="medlineplus_consumer_health",
        domain="lifestyle",
        provenance_complete=True,
    ) is False


def test_finalize_eligibility_low_risk_explicit_domain(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-dedupe-1")
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    assert elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert ku.medical_safety_state == MedicalSafetyState.CLEARED.value


def test_finalize_eligibility_missing_domain_not_auto_eligible():
    ku = SimpleNamespace(
        provenance_complete=True,
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=MedicalSafetyState.PENDING_REVIEW.value,
        conflict_state=ConflictState.NONE.value,
        freshness_state=FreshnessState.UNKNOWN.value,
        review_state=ReviewState.NOT_REVIEWED.value,
        publication_state=PublicationState.DRAFT.value,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
        retraction_reason=None,
    )
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain=None)
    assert elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE


def test_finalize_eligibility_unknown_domain_not_auto_eligible(db):
    ku = _make_ku(db, domain="unknown", dedupe_key="s49-unknown-domain")
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="unknown")
    assert elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE


def test_finalize_eligibility_high_risk_domain_review_required(db):
    ku = _make_ku(db, domain="diabetes", dedupe_key="s49-diabetes")
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="diabetes")
    assert elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE


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
        deduplication_key=hashlib.sha256(b"s49-pubmed").hexdigest(),
        canonical_hash=hashlib.sha256(b"s49-pubmed").hexdigest(),
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


def test_lexical_only_indexing_zero_vector_generation(db):
    from backend.app.services.scis.serving_bridge import index_eligible_knowledge_unit_if_ready

    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-lexical-only")
    apply_governed_low_risk_fields(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    ku.runtime_eligibility = elig.value
    db.flush()

    source_profile_id, raw_evidence_id = _seed_lineage_fixtures(db, suffix="s49-lexical-only")
    _link_ku_provenance(db, ku, source_profile_id=source_profile_id, raw_evidence_id=raw_evidence_id)
    with patch(
        "backend.app.services.scis.embedding.providers.FakeScisEmbeddingProvider.embed_texts"
    ) as mock_embed, patch.object(db, "commit", db.flush):
        rows = index_eligible_knowledge_unit_if_ready(
            db, ku, source_profile_id=source_profile_id, raw_evidence_id=raw_evidence_id
        )
        mock_embed.assert_not_called()

    assert len(rows) >= 1
    for row in rows:
        assert row.model_identifier == LEXICAL_ONLY_MODEL_ID
        assert row.backend_kind == LEXICAL_ONLY_BACKEND_KIND
        assert row.embedding_json is None
        assert row.source_profile_id == source_profile_id
        assert row.raw_evidence_id == raw_evidence_id
        vec = db.execute(
            text("SELECT embedding_vector FROM knowledge_chunk_embeddings WHERE id = :id"),
            {"id": row.id},
        ).scalar()
        assert vec is None


def test_ku_to_kce_lexical_retrieval_with_provenance(db):
    from backend.app.services.scis.serving_bridge import index_eligible_knowledge_unit_if_ready

    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-scis")
    ku.normalized_statement = "NHS live well exercise guidance for healthy adults."
    apply_governed_low_risk_fields(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    ku.runtime_eligibility = elig.value
    db.flush()

    source_profile_id, raw_evidence_id = _seed_lineage_fixtures(db, suffix="s49-scis")
    _link_ku_provenance(db, ku, source_profile_id=source_profile_id, raw_evidence_id=raw_evidence_id)
    with patch.object(db, "commit", db.flush):
        rows = index_eligible_knowledge_unit_if_ready(
            db, ku, source_profile_id=source_profile_id, raw_evidence_id=raw_evidence_id
        )
    assert len(rows) >= 1

    resp = retrieve(
        db,
        ScisRetrievalRequest(
            query_text="NHS live well exercise",
            top_k=5,
            retrieval_mode=RetrievalMode.LEXICAL,
            allowed_knowledge_classes=["GLOBAL_GOVERNED_KNOWLEDGE"],
        ),
    )
    if resp.evidence:
        item = resp.evidence[0]
        assert item.provenance.knowledge_unit_id == int(ku.id)
        assert item.provenance.chunk_id is not None


def test_existing_ku_provenance_complete_reevaluated_eligible_and_indexed(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-existing-reeval")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-existing-reeval", canonical_key="nhs_uk_live_well"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    elig = _apply_existing_ku_path(
        db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov
    )
    assert elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE
    first_count = _kce_count(db, ku.id)
    assert first_count >= 1


def test_existing_ku_lexical_index_idempotent(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-existing-idempotent")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-existing-idempotent", canonical_key="nhs_uk_live_well"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    _apply_existing_ku_path(db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov)
    first_count = _kce_count(db, ku.id)
    _apply_existing_ku_path(db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov)
    assert _kce_count(db, ku.id) == first_count


def test_existing_ku_provenance_source_mismatch_not_promoted(db):
    from backend.app.services.i5.governed_ku_serving import apply_governed_finalize_and_lexical_index

    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-existing-mismatch")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    auth_gsp_id, auth_raw_id = _seed_lineage_fixtures(
        db, suffix="s49-auth-pubmed", canonical_key="pubmed_ncbi_eutils"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=auth_gsp_id, raw_evidence_id=auth_raw_id)
    incoming_gsp_id, incoming_raw_id = _seed_lineage_fixtures(
        db, suffix="s49-incoming-nhs", canonical_key="nhs_uk_live_well"
    )

    with patch.object(db, "commit", db.flush):
        elig = apply_governed_finalize_and_lexical_index(
            db,
            ku,
            source_key="nhs_uk_live_well",
            source_profile_id=incoming_gsp_id,
            raw_evidence_id=incoming_raw_id,
            authoritative_provenance=prov,
            incoming_source_profile_id=incoming_gsp_id,
        )
    assert elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert _kce_count(db, ku.id) == 0


def test_existing_ku_high_risk_domain_not_promoted(db):
    ku = _make_ku(db, domain="diabetes", dedupe_key="s49-existing-diabetes")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-existing-diabetes", canonical_key="nhs_uk_live_well"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)
    elig = _apply_existing_ku_path(
        db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov
    )
    assert elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert _kce_count(db, ku.id) == 0


def test_existing_ku_pubmed_connector_not_promoted(db):
    ku = _make_ku(db, domain="neurology", dedupe_key="s49-existing-pubmed")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-existing-pubmed", canonical_key="pubmed_ncbi_eutils"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)
    elig = _apply_existing_ku_path(
        db, ku, source_key="pubmed_ncbi_eutils", gsp_id=gsp_id, raw_id=raw_id, prov=prov
    )
    assert elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert _kce_count(db, ku.id) == 0


def test_existing_ku_unknown_domain_not_promoted(db):
    ku = _make_ku(db, domain="unknown", dedupe_key="s49-existing-unknown-domain")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-existing-unknown-domain", canonical_key="nhs_uk_live_well"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)
    elig = _apply_existing_ku_path(
        db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov
    )
    assert elig != KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert _kce_count(db, ku.id) == 0


def test_existing_ku_already_eligible_indexed_no_duplicate(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-existing-already-indexed")
    apply_governed_low_risk_fields(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    ku.runtime_eligibility = elig.value
    ku.provenance_complete = True
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-existing-already-indexed", canonical_key="nhs_uk_live_well"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)
    _apply_existing_ku_path(db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov)
    first_count = _kce_count(db, ku.id)
    _apply_existing_ku_path(db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov)
    assert _kce_count(db, ku.id) == first_count


def test_existing_ku_lexical_index_zero_vector_writes(db):
    from backend.app import models
    from backend.app.services.scis.lexical_indexing import LEXICAL_ONLY_MODEL_ID

    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-existing-zero-vector")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-existing-zero-vector", canonical_key="nhs_uk_live_well"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    with patch(
        "backend.app.services.scis.embedding.providers.FakeScisEmbeddingProvider.embed_texts"
    ) as mock_embed:
        _apply_existing_ku_path(
            db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov
        )
        mock_embed.assert_not_called()

    rows = db.query(models.KnowledgeChunkEmbedding).filter_by(knowledge_unit_id=ku.id).all()
    assert rows
    for row in rows:
        assert row.model_identifier == LEXICAL_ONLY_MODEL_ID
        vec = db.execute(
            text("SELECT embedding_vector FROM knowledge_chunk_embeddings WHERE id = :id"),
            {"id": row.id},
        ).scalar()
        assert vec is None


def _reevaluate_unchanged(db, source_profile_id: int):
    from backend.app.services.i5.governed_ku_serving import reevaluate_existing_kus_for_unchanged_source

    with patch.object(db, "commit", db.flush):
        return reevaluate_existing_kus_for_unchanged_source(db, source_profile_id=int(source_profile_id))


def _entity_counts(db):
    from backend.app import models

    return {
        "raw": db.query(models.I5RawEvidence).count(),
        "provenance": db.query(models.KnowledgeProvenance).count(),
        "candidate": db.query(models.KnowledgeUnit).count(),
    }


def test_unchanged_source_304_reevaluates_not_eligible_ku_to_eligible_with_lexical_kce(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r05-304-reeval")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-reeval", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    result = _reevaluate_unchanged(db, gsp_id)
    assert result.examined == 1
    assert result.newly_eligible == 1
    assert result.newly_indexed == 1
    assert ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value
    assert _kce_count(db, ku.id) >= 1


def test_unchanged_source_repeat_run_idempotent_lexical_kce(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r05-304-idempotent")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-idempotent", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    _reevaluate_unchanged(db, gsp_id)
    first_count = _kce_count(db, ku.id)
    assert first_count >= 1
    _reevaluate_unchanged(db, gsp_id)
    assert _kce_count(db, ku.id) == first_count


def test_unchanged_source_provenance_mismatch_not_promoted(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r05-304-mismatch")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    auth_gsp_id, auth_raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-auth-pubmed", canonical_key="pubmed_ncbi_eutils"
    )
    _link_ku_provenance(db, ku, source_profile_id=auth_gsp_id, raw_evidence_id=auth_raw_id)
    incoming_gsp_id, _ = _seed_lineage_fixtures(
        db, suffix="s49-r05-incoming-nhs", canonical_key="nhs_uk_live_well"
    )

    result = _reevaluate_unchanged(db, incoming_gsp_id)
    assert result.newly_eligible == 0
    assert ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    assert _kce_count(db, ku.id) == 0


def test_unchanged_source_high_risk_domain_not_promoted(db):
    ku = _make_ku(db, domain="diabetes", dedupe_key="s49-r05-304-diabetes")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-diabetes", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    result = _reevaluate_unchanged(db, gsp_id)
    assert result.newly_eligible == 0
    assert _kce_count(db, ku.id) == 0


def test_unchanged_source_unknown_domain_not_promoted(db):
    ku = _make_ku(db, domain="unknown", dedupe_key="s49-r05-304-unknown-domain")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-unknown-domain", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    result = _reevaluate_unchanged(db, gsp_id)
    assert result.newly_eligible == 0
    assert _kce_count(db, ku.id) == 0


def test_unchanged_source_retracted_ku_not_promoted(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r05-304-retracted")
    ku.provenance_complete = True
    ku.retraction_reason = "withdrawn"
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-retracted", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    result = _reevaluate_unchanged(db, gsp_id)
    assert result.newly_eligible == 0
    assert _kce_count(db, ku.id) == 0


def test_unchanged_source_conflicted_ku_not_promoted(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r05-304-conflicted")
    ku.provenance_complete = True
    ku.conflict_state = ConflictState.CONFIRMED.value
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-conflicted", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    result = _reevaluate_unchanged(db, gsp_id)
    assert result.newly_eligible == 0
    assert _kce_count(db, ku.id) == 0


def test_unchanged_source_pubmed_connector_not_promoted(db):
    ku = _make_ku(db, domain="neurology", dedupe_key="s49-r05-304-pubmed")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-pubmed", canonical_key="pubmed_ncbi_eutils"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    result = _reevaluate_unchanged(db, gsp_id)
    assert result.examined == 0
    assert result.newly_eligible == 0
    assert _kce_count(db, ku.id) == 0


def test_unchanged_source_path_creates_no_new_raw_provenance_or_candidate(db):
    from backend.app import models
    from backend.app.services.i5 import weekly_orchestrator as orch
    from backend.app.services.i5.adapters.base import FixtureTransportResponse
    from backend.app.services.i5.source_discovery import SourceCandidateDescriptor, plan_discovery

    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r05-304-no-writes")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-no-writes", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)
    before = _entity_counts(db)

    status, code, handoffs = orch._apply_fixture_source(
        work=plan_discovery(
            [
                SourceCandidateDescriptor(
                    source_profile_id=gsp_id,
                    adapter_mode="PUBLIC_WEB_FETCH",
                    url="https://www.nhs.uk/live-well/exercise/s49-r05-304-no-writes/",
                    registry_state="ACTIVE",
                    runtime_eligibility="ELIGIBLE",
                    rights_terms_state="ACCEPTABLE",
                    robots_access_state="ALLOWED",
                    rate_limit_policy="DEFINED",
                    allowed_domain="nhs.uk",
                    canonical_key="nhs_uk_live_well",
                )
            ]
        ).selected[0],
        transports={
            gsp_id: FixtureTransportResponse(status_code=304, body=b"", etag='"same"'),
        },
    )
    assert status == "SKIPPED"
    assert code == "NO_MATERIAL_CHANGE"
    assert handoffs == []

    _reevaluate_unchanged(db, gsp_id)
    after = _entity_counts(db)
    assert after == before
    assert db.query(models.KnowledgeUnit).count() == before["candidate"]


def test_unchanged_source_reevaluation_preserves_provenance_citation_and_zero_vectors(db):
    from backend.app import models

    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r05-304-citation")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r05-304-citation", canonical_key="nhs_uk_live_well"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)
    citation_before = prov.citation_rendering_data

    with patch(
        "backend.app.services.scis.embedding.providers.FakeScisEmbeddingProvider.embed_texts"
    ) as mock_embed:
        _reevaluate_unchanged(db, gsp_id)
        mock_embed.assert_not_called()

    db.refresh(prov)
    assert prov.citation_rendering_data == citation_before
    rows = db.query(models.KnowledgeChunkEmbedding).filter_by(knowledge_unit_id=ku.id).all()
    assert len(rows) >= 1
    for row in rows:
        assert row.model_identifier == LEXICAL_ONLY_MODEL_ID
        vec = db.execute(
            text("SELECT embedding_vector FROM knowledge_chunk_embeddings WHERE id = :id"),
            {"id": row.id},
        ).scalar()
        assert vec is None


def _orchestrate_fixture_304(db, *, gsp_id: int, url: str, logical_run_key: str):
    import importlib

    from backend.app.services.i5 import weekly_orchestrator as orch
    from backend.app.services.i5.adapters.base import FixtureTransportResponse
    from backend.app.services.i5.source_discovery import SourceCandidateDescriptor

    models = importlib.import_module("backend.app.models")
    candidate = SourceCandidateDescriptor(
        source_profile_id=gsp_id,
        adapter_mode="PUBLIC_WEB_FETCH",
        url=url,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="ACCEPTABLE",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain="nhs.uk",
        canonical_key="nhs_uk_live_well",
    )
    with patch.object(db, "commit", db.flush):
        return orch.orchestrate_weekly_run(
            db,
            models,
            candidates=[candidate],
            transports={
                gsp_id: FixtureTransportResponse(status_code=304, body=b"", etag='"same"'),
            },
            dry_run=False,
            persist_ledger=True,
            logical_run_key=logical_run_key,
        )


def test_unchanged_source_no_mutation_production_write_false(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r06-no-mutation")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r06-no-mutation", canonical_key="nhs_uk_live_well"
    )
    prov = _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)
    _apply_existing_ku_path(db, ku, source_key="nhs_uk_live_well", gsp_id=gsp_id, raw_id=raw_id, prov=prov)
    assert ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value
    assert _kce_count(db, ku.id) >= 1

    outcome = _orchestrate_fixture_304(
        db,
        gsp_id=gsp_id,
        url="https://www.nhs.uk/live-well/exercise/s49-r06-no-mutation/",
        logical_run_key=f"s49-r06-no-mutation-{uuid.uuid4().hex}",
    )
    assert outcome.production_write is False
    assert outcome.unchanged_source_examined >= 1
    assert outcome.unchanged_source_newly_eligible == 0
    assert outcome.unchanged_source_newly_indexed == 0


def test_unchanged_source_newly_eligible_production_write_true(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r06-newly-eligible")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r06-newly-eligible", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    outcome = _orchestrate_fixture_304(
        db,
        gsp_id=gsp_id,
        url="https://www.nhs.uk/live-well/exercise/s49-r06-newly-eligible/",
        logical_run_key=f"s49-r06-newly-eligible-{uuid.uuid4().hex}",
    )
    assert outcome.production_write is True
    assert outcome.unchanged_source_newly_eligible >= 1
    assert ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value


def test_unchanged_source_newly_indexed_production_write_true(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r06-newly-indexed")
    apply_governed_low_risk_fields(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    elig = finalize_governed_runtime_eligibility(ku, source_key="nhs_uk_live_well", domain="lifestyle")
    ku.runtime_eligibility = elig.value
    ku.provenance_complete = True
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r06-newly-indexed", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)
    assert _kce_count(db, ku.id) == 0

    outcome = _orchestrate_fixture_304(
        db,
        gsp_id=gsp_id,
        url="https://www.nhs.uk/live-well/exercise/s49-r06-newly-indexed/",
        logical_run_key=f"s49-r06-newly-indexed-{uuid.uuid4().hex}",
    )
    assert outcome.production_write is True
    assert outcome.unchanged_source_newly_indexed >= 1
    assert _kce_count(db, ku.id) >= 1


def test_unchanged_source_idempotent_repeat_production_write_false(db):
    ku = _make_ku(db, domain="lifestyle", dedupe_key="s49-r06-idempotent-write")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r06-idempotent-write", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    first = _orchestrate_fixture_304(
        db,
        gsp_id=gsp_id,
        url="https://www.nhs.uk/live-well/exercise/s49-r06-idempotent-write/",
        logical_run_key=f"s49-r06-idempotent-write-a-{uuid.uuid4().hex}",
    )
    assert first.production_write is True
    kce_count = _kce_count(db, ku.id)

    second = _orchestrate_fixture_304(
        db,
        gsp_id=gsp_id,
        url="https://www.nhs.uk/live-well/exercise/s49-r06-idempotent-write/",
        logical_run_key=f"s49-r06-idempotent-write-b-{uuid.uuid4().hex}",
    )
    assert second.production_write is False
    assert _kce_count(db, ku.id) == kce_count


def test_unchanged_source_governance_blocked_production_write_false(db):
    ku = _make_ku(db, domain="diabetes", dedupe_key="s49-r06-governance-blocked")
    ku.provenance_complete = True
    ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
    db.flush()

    gsp_id, raw_id = _seed_lineage_fixtures(
        db, suffix="s49-r06-governance-blocked", canonical_key="nhs_uk_live_well"
    )
    _link_ku_provenance(db, ku, source_profile_id=gsp_id, raw_evidence_id=raw_id)

    outcome = _orchestrate_fixture_304(
        db,
        gsp_id=gsp_id,
        url="https://www.nhs.uk/live-well/exercise/s49-r06-governance-blocked/",
        logical_run_key=f"s49-r06-governance-blocked-{uuid.uuid4().hex}",
    )
    assert outcome.production_write is False
    assert outcome.unchanged_source_skipped_fail_closed >= 1
    assert ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
