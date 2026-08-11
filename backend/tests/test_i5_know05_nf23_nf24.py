"""I5-KNOW-05 NF23/NF24 — rights truth + governance truth + trial semantics."""

from __future__ import annotations

import hashlib
import json
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeType,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
    ReviewState,
)
from backend.app.services.i5.know05.bounded_ingestion import ingest_clinicaltrials_bounded
from backend.app.services.i5.know05.canonical_rights import (
    OP_DERIVED_METADATA_PERSIST,
    count_synthetic_product_rights_sources,
    evaluate_connector_operation_rights,
)
from backend.app.services.i5.know05.eligibility_integrity import (
    audit_eligibility_integrity,
    count_synthetic_governance_auto_promotions,
)
from backend.app.services.i5.know05.modes import Know05Mode
from backend.app.services.i5.know05.publication import (
    PublicationCandidate,
    PublicationGateEvidence,
    PublicationPipelineError,
    PublicationStage,
    advance_stage,
    apply_proven_gates,
    derive_clinical_runtime_eligible,
)
from backend.app.services.i5.know05.source_selection import select_connectors_for_gap
from backend.app.services.i5.know05.coverage_engine import CoveragePrioritizationItem
from backend.tests._know05_test_fixtures import (
    seed_canonical_source_with_rights,
    seed_source_governance_approval,
)


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _require_065(engine):
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head != "065_i5_know04_connectors_change_intelligence":
            pytest.skip(f"alembic head {head} != 065")


def _fake_ctgov_http(nct: str = "NCT00999999", title: str = "Know05 rights canary"):
    study = {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": title},
            "statusModule": {"overallStatus": "RECRUITING"},
        }
    }

    class _Resp:
        def __init__(self, payload: dict, status=200):
            self.status_code = status
            self.headers = {"Content-Type": "application/json"}
            self.content = json.dumps(payload).encode()

        def json(self):
            return json.loads(self.content.decode())

    def fake_get(url, headers=None, timeout=None, params=None):
        if "/studies/" in str(url) and "NCT" in str(url):
            return _Resp(study)
        return _Resp({"totalCount": 1, "studies": [study]})

    return fake_get


def test_nf23_advance_stage_does_not_fabricate_gates():
    c = PublicationCandidate(external_identifier="x", source_connector_key="clinicaltrials_gov_api_v2")
    c = advance_stage(c, PublicationStage.NORMALIZED_CANDIDATE)
    assert c.provenance_complete is False
    assert c.governance_approved is False
    with pytest.raises(PublicationPipelineError):
        # cannot jump to runtime
        advance_stage(c, PublicationStage.RUNTIME_ELIGIBILITY)


def test_nf23_clinical_runtime_unknown_safety_fail_closed():
    ok, reason = derive_clinical_runtime_eligible(
        artifact_type="ARTICLE",
        medical_safety_state=MedicalSafetyState.UNKNOWN.value,
        provenance_complete=True,
        evidence_linked=True,
        conflict_clear=True,
        safety_clear=False,
        governance_approved=True,
        rights_allowed=True,
    )
    assert ok is False
    assert "UNKNOWN_SAFETY" in reason


def test_nf23_trial_registry_never_clinical_runtime():
    ok, reason = derive_clinical_runtime_eligible(
        artifact_type="CLINICAL_TRIAL_RECORD",
        medical_safety_state=MedicalSafetyState.CLEARED.value,
        provenance_complete=True,
        evidence_linked=True,
        conflict_clear=True,
        safety_clear=True,
        governance_approved=True,
        rights_allowed=True,
    )
    assert ok is False
    assert "TRIAL_REGISTRATION" in reason


def test_nf20_selection_does_not_infer_rights_from_connector_key_alone():
    class _FakeDB:
        def query(self, model):
            class _Q:
                def filter_by(self, **_kw):
                    return self

                def first(self):
                    return None

            return _Q()

    item = CoveragePrioritizationItem(
        cell_id=1,
        concept_id=1,
        dimension_code="CLINICAL_TRIALS",
        evidence_class="CLINICAL_TRIALS",
        cell_state="MISSING",
        priority="P0",
        p0_overlay=True,
        gap_key="ms-trials",
    )
    sels = select_connectors_for_gap(_FakeDB(), item)
    assert sels
    ct = [s for s in sels if s.connector_key == "clinicaltrials_gov_api_v2"][0]
    assert ct.connector_capability_state == "CONNECTOR_READY"
    assert ct.rights_state in {"RIGHTS_UNKNOWN", "RIGHTS_BLOCKED"}
    assert ct.automation_decision == "BLOCKED"
    assert ct.block_reason


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_t1_unknown_rights_blocks_persist_no_synthetic_gsp():
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_canonical_source_with_rights(db, rights_mode="UNKNOWN")
        db.flush()
        before = count_synthetic_product_rights_sources(db)
        r = ingest_clinicaltrials_bounded(
            db,
            mode=Know05Mode.BOUNDED_INGESTION,
            http_get=_fake_ctgov_http(),
            max_records=1,
            persist=True,
        )
        db.commit()
        assert r.status == "BLOCKED"
        assert r.storage_decision == "NO_STORE"
        assert r.rights_decision == "RIGHTS_UNKNOWN"
        assert "UNKNOWN" in (r.block_reason or "") or "RIGHTS" in (r.block_reason or "") or "RETAIN" in (r.block_reason or "") or "MODE" in (r.block_reason or "") or "FAIL_CLOSED" in (r.block_reason or "")
        assert count_synthetic_product_rights_sources(db) == before
        assert not any(
            x.canonical_key.startswith("know05:rehearsal:")
            for x in db.query(models.GovernedSourceProfile).all()
            if x.canonical_key
        )
    finally:
        db.close()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_t2_denied_rights_blocks_persist():
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        seed_canonical_source_with_rights(db, rights_mode="DENIED")
        db.flush()
        r = ingest_clinicaltrials_bounded(
            db,
            mode=Know05Mode.BOUNDED_INGESTION,
            http_get=_fake_ctgov_http("NCT00999991"),
            max_records=1,
            persist=True,
        )
        db.commit()
        assert r.status == "BLOCKED"
        assert r.storage_decision == "NO_STORE"
        assert r.rights_decision in {"RIGHTS_BLOCKED", "RIGHTS_UNKNOWN"}
        assert r.clinical_runtime_eligible is False
    finally:
        db.close()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_t4_t6_allowed_rights_store_trial_not_clinical_runtime():
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        gsp = seed_canonical_source_with_rights(db, rights_mode="ALLOWED")
        # No governance approval yet — store OK for derived metadata; clinical runtime false
        db.flush()
        rights = evaluate_connector_operation_rights(
            db, connector_key="clinicaltrials_gov_api_v2", operation=OP_DERIVED_METADATA_PERSIST
        )
        assert rights.automation_decision == "AUTOMATION_ALLOWED"
        r = ingest_clinicaltrials_bounded(
            db,
            mode=Know05Mode.BOUNDED_INGESTION,
            http_get=_fake_ctgov_http("NCT00999992", "Stored trial"),
            max_records=1,
            persist=True,
        )
        db.commit()
        assert r.status == "STORED", r.as_dict()
        assert r.storage_decision == "DERIVED_GOVERNED_STORE"
        assert r.clinical_runtime_eligible is False
        assert r.synthetic_product_rights_source is False
        ku = db.query(models.KnowledgeUnit).filter_by(id=r.knowledge_unit_id).first()
        assert ku is not None
        assert ku.runtime_eligibility == KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value
        assert ku.medical_safety_state == MedicalSafetyState.UNKNOWN.value
        art = db.query(models.I5ScientificArtifact).filter_by(id=r.artifact_id).first()
        assert art.artifact_type == "CLINICAL_TRIAL_RECORD"
        assert count_synthetic_product_rights_sources(db) == 0

        # T3: governance missing → clinical runtime false (already)
        assert not r.clinical_runtime_eligible

        report = audit_eligibility_integrity(db)
        assert report.trial_registry_as_treatment_recommendation == 0
        assert report.eligible_with_unknown_safety == 0
        assert report.synthetic_product_rights_source_count == 0
    finally:
        db.close()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_t7_real_governed_positive_non_trial_fixture():
    """Positive clinical runtime only when all gates are explicitly established (not trial)."""
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        gsp = seed_canonical_source_with_rights(db, connector_key="who_guideline_catalogue", rights_mode="ALLOWED")
        # Fix authority class for guideline
        ext = db.query(models.I5SourceRegistryExtension).filter_by(source_profile_id=gsp.id).first()
        ext.authority_class = "SPECIALTY_GUIDELINE_BODY"
        seed_source_governance_approval(db, source_profile_id=gsp.id)
        statement = "Positive governed fixture statement for KNOW-05 T7."
        ku = models.KnowledgeUnit(
            canonical_unit_id=hashlib.sha256(b"t7").hexdigest()[:32],
            immutable_version_id="v1",
            domain="guidelines",
            knowledge_type=KnowledgeType.FACT.value,
            normalized_statement=statement,
            evidence_strength=EvidenceStrength.MODERATE.value,
            medical_safety_state=MedicalSafetyState.CLEARED.value,
            conflict_state=ConflictState.NONE.value,
            freshness_state=FreshnessState.CURRENT.value,
            review_state=ReviewState.APPROVED.value,
            publication_state=PublicationState.PUBLISHED.value,
            runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
            provenance_complete=False,
            canonical_hash=hashlib.sha256(statement.encode()).hexdigest(),
            deduplication_key=hashlib.sha256(b"t7-dedupe").hexdigest(),
            hash_algorithm="SHA-256",
            canonicalization_version="v1",
        )
        db.add(ku)
        db.flush()
        art = models.I5ScientificArtifact(
            artifact_key="t7:guideline:1",
            artifact_type="GUIDELINE",
            title="T7",
            source_profile_id=gsp.id,
        )
        db.add(art)
        db.flush()
        ver = models.I5ScientificArtifactVersion(
            artifact_id=art.id, version_label="v1", content_hash=hashlib.sha256(b"t7").hexdigest(), version_state="PUBLISHED"
        )
        db.add(ver)
        db.flush()
        db.add(
            models.KnowledgeProvenance(
                knowledge_unit_id=ku.id,
                source_profile_id=gsp.id,
                retrieval_method="test_fixture",
                access_route="TEST",
                content_hash=hashlib.sha256(b"t7").hexdigest(),
            )
        )
        db.add(
            models.I5KnowledgeUnitEvidenceLink(
                knowledge_unit_id=ku.id,
                artifact_version_id=ver.id,
                support_direction="SUPPORTS",
                evidence_role="PRIMARY",
            )
        )
        db.flush()
        ku.provenance_complete = True
        # Derive eligibility via publication helpers — product code must not invent flags
        gates = PublicationGateEvidence(
            provenance_complete=True,
            evidence_linked=True,
            conflict_clear=True,
            safety_clear=True,
            governance_approved=True,
            clinical_runtime_allowed=False,
        )
        ok, reason = derive_clinical_runtime_eligible(
            artifact_type="GUIDELINE",
            medical_safety_state=ku.medical_safety_state,
            provenance_complete=True,
            evidence_linked=True,
            conflict_clear=True,
            safety_clear=True,
            governance_approved=True,
            rights_allowed=True,
        )
        assert ok is True, reason
        ku.runtime_eligibility = KnowledgeUnitRuntimeEligibility.ELIGIBLE.value
        db.flush()
        cand = PublicationCandidate(
            external_identifier="t7",
            source_connector_key="who_guideline_catalogue",
            artifact_type="GUIDELINE",
            medical_safety_state=ku.medical_safety_state,
        )
        apply_proven_gates(cand, gates)
        assert cand.governance_approved is True
        assert cand.safety_clear is True
        report = audit_eligibility_integrity(db)
        assert report.eligible_with_unknown_safety == 0
        assert report.eligible_without_provenance == 0
        assert report.eligible_with_blocked_rights == 0
        assert report.eligible_without_real_governance == 0
        # NF25 positive control: valid governed ELIGIBLE → computed final zero
        assert report.synthetic_governance_auto_promotion_count == 0
        assert count_synthetic_governance_auto_promotions(db) == 0
        assert "DB_DERIVED" in report.computation_basis
        assert "literal" not in report.computation_basis.lower()
        print(
            f"SYNTHETIC_GOVERNANCE_AUTO_PROMOTION_COUNT={report.synthetic_governance_auto_promotion_count}"
            f" COMPUTATION_BASIS={report.computation_basis}"
        )
        db.commit()
    finally:
        db.close()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_nf25_negative_bypass_eligible_without_governance_detected():
    """NF25 negative control: deliberately invalid ELIGIBLE KU without real governance.

    Injected state MUST NEVER exist in valid production operation. Audit must detect
    synthetic_governance_auto_promotion_count increase from real DB inspection — not a constant.
    """
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        before = audit_eligibility_integrity(db)
        before_synth = before.synthetic_governance_auto_promotion_count

        # Dedicated connector so suite-shared GSPs (e.g. T7 WHO) cannot supply governance.
        gsp = seed_canonical_source_with_rights(
            db, connector_key="nf25_bypass_fixture_source", rights_mode="ALLOWED"
        )
        ext = db.query(models.I5SourceRegistryExtension).filter_by(source_profile_id=gsp.id).first()
        if ext is not None:
            ext.authority_class = "SPECIALTY_GUIDELINE_BODY"
        statement = "NF25 negative fixture: ELIGIBLE without source governance."
        ku = models.KnowledgeUnit(
            canonical_unit_id=hashlib.sha256(b"nf25-neg").hexdigest()[:32],
            immutable_version_id="v1",
            domain="guidelines",
            knowledge_type=KnowledgeType.FACT.value,
            normalized_statement=statement,
            evidence_strength=EvidenceStrength.MODERATE.value,
            medical_safety_state=MedicalSafetyState.CLEARED.value,
            conflict_state=ConflictState.NONE.value,
            freshness_state=FreshnessState.CURRENT.value,
            review_state=ReviewState.APPROVED.value,
            publication_state=PublicationState.PUBLISHED.value,
            # Deliberate bypass injection — product path must not create this.
            runtime_eligibility=KnowledgeUnitRuntimeEligibility.ELIGIBLE.value,
            provenance_complete=True,
            canonical_hash=hashlib.sha256(statement.encode()).hexdigest(),
            deduplication_key=hashlib.sha256(b"nf25-neg-dedupe").hexdigest(),
            hash_algorithm="SHA-256",
            canonicalization_version="v1",
        )
        db.add(ku)
        db.flush()
        db.add(
            models.KnowledgeProvenance(
                knowledge_unit_id=ku.id,
                source_profile_id=gsp.id,
                retrieval_method="nf25_negative_fixture",
                access_route="TEST",
                content_hash=hashlib.sha256(b"nf25-neg").hexdigest(),
            )
        )
        db.flush()

        gov_rows = (
            db.query(models.I5GovernanceDecision)
            .filter_by(entity_type="SOURCE_PROFILE", entity_id=gsp.id, outcome="APPROVED")
            .count()
        )
        assert gov_rows == 0

        report = audit_eligibility_integrity(db)
        assert report.synthetic_governance_auto_promotion_count == before_synth + 1
        assert report.eligible_without_real_governance == before.eligible_without_real_governance + 1
        assert (
            report.synthetic_governance_auto_promotion_count
            == report.eligible_without_real_governance
        )
        assert count_synthetic_governance_auto_promotions(db) == report.synthetic_governance_auto_promotion_count
        assert report.synthetic_governance_auto_promotion_count > 0
        print(
            f"SYNTHETIC_GOVERNANCE_AUTO_PROMOTION_COUNT={report.synthetic_governance_auto_promotion_count}"
            f" ELIGIBLE_WITHOUT_REAL_GOVERNANCE={report.eligible_without_real_governance}"
            f" COMPUTATION_BASIS={report.computation_basis}"
        )
        db.rollback()
    finally:
        db.close()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_nf25_positive_governed_zero_from_actual_audit():
    """NF25 positive control: governed ELIGIBLE does not increase synthetic auto-promotion count."""
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        before = audit_eligibility_integrity(db)
        before_synth = before.synthetic_governance_auto_promotion_count

        gsp = seed_canonical_source_with_rights(
            db, connector_key="nf25_governed_fixture_source", rights_mode="ALLOWED"
        )
        ext = db.query(models.I5SourceRegistryExtension).filter_by(source_profile_id=gsp.id).first()
        if ext is not None:
            ext.authority_class = "SPECIALTY_GUIDELINE_BODY"
        seed_source_governance_approval(db, source_profile_id=gsp.id)
        statement = "NF25 positive fixture: ELIGIBLE with real source governance."
        ku = models.KnowledgeUnit(
            canonical_unit_id=hashlib.sha256(b"nf25-pos").hexdigest()[:32],
            immutable_version_id="v1",
            domain="guidelines",
            knowledge_type=KnowledgeType.FACT.value,
            normalized_statement=statement,
            evidence_strength=EvidenceStrength.MODERATE.value,
            medical_safety_state=MedicalSafetyState.CLEARED.value,
            conflict_state=ConflictState.NONE.value,
            freshness_state=FreshnessState.CURRENT.value,
            review_state=ReviewState.APPROVED.value,
            publication_state=PublicationState.PUBLISHED.value,
            runtime_eligibility=KnowledgeUnitRuntimeEligibility.ELIGIBLE.value,
            provenance_complete=True,
            canonical_hash=hashlib.sha256(statement.encode()).hexdigest(),
            deduplication_key=hashlib.sha256(b"nf25-pos-dedupe").hexdigest(),
            hash_algorithm="SHA-256",
            canonicalization_version="v1",
        )
        db.add(ku)
        db.flush()
        db.add(
            models.KnowledgeProvenance(
                knowledge_unit_id=ku.id,
                source_profile_id=gsp.id,
                retrieval_method="nf25_positive_fixture",
                access_route="TEST",
                content_hash=hashlib.sha256(b"nf25-pos").hexdigest(),
            )
        )
        db.flush()
        report = audit_eligibility_integrity(db)
        # Governed ELIGIBLE must not contribute to the synthetic auto-promotion invariant.
        assert report.synthetic_governance_auto_promotion_count == before_synth
        assert report.eligible_without_real_governance == before.eligible_without_real_governance
        assert count_synthetic_governance_auto_promotions(db) == report.synthetic_governance_auto_promotion_count
        assert "DB_DERIVED" in report.computation_basis
        # On a clean suite baseline this is the final computed zero; still assert absolute zero
        # for the contribution of this governed fixture itself (delta == 0).
        print(
            f"SYNTHETIC_GOVERNANCE_AUTO_PROMOTION_COUNT={report.synthetic_governance_auto_promotion_count}"
            f" DELTA_FROM_GOVERNED_FIXTURE=0"
            f" COMPUTATION_BASIS={report.computation_basis}"
        )
        db.rollback()
    finally:
        db.close()
