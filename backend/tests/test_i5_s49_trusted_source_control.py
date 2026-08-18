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


def _seed_lineage_fixtures(db, *, suffix: str | None = None) -> tuple[int, int]:
    from backend.app import models

    token = suffix or uuid.uuid4().hex
    gsp = models.GovernedSourceProfile(
        canonical_key=f"s49-gsp-{_canonical_hash(token)[:24]}",
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


def _link_ku_provenance(db, ku, *, source_profile_id: int, raw_evidence_id: int) -> None:
    from backend.app import models

    db.add(
        models.KnowledgeProvenance(
            knowledge_unit_id=ku.id,
            source_profile_id=source_profile_id,
            raw_evidence_id=raw_evidence_id,
            retrieval_method="TEST_FIXTURE",
            access_route="TEST",
            content_hash=_canonical_hash(f"prov-{ku.id}"),
        )
    )
    db.flush()


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
            mode=RetrievalMode.LEXICAL_ONLY,
            allowed_knowledge_classes=["GLOBAL_GOVERNED_KNOWLEDGE"],
        ),
    )
    if resp.evidence_items:
        item = resp.evidence_items[0]
        assert item.provenance.knowledge_unit_id == int(ku.id)
        assert item.provenance.chunk_id is not None
