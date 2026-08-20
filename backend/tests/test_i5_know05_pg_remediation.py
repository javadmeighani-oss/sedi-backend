"""I5-KNOW-05 PG remediation — NF18 negative controls + NF19 bounded ingestion E2E."""

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
    CoverageCellState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeType,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    ProcessingPermissionMode,
    PublicationState,
    ReviewState,
    RightDecision,
)
from backend.app.services.i5.know02.taxonomy import ensure_dimension, upsert_coverage_cell
from backend.app.services.i5.know05.authority_audit import audit_knowledge_authority
from backend.app.services.i5.know05.availability import derive_ku_availability
from backend.app.services.i5.know05.bounded_ingestion import ingest_clinicaltrials_bounded
from backend.app.services.i5.know05.modes import Know05Mode
from backend.app.services.i5.know05.orchestrator import run_know05_cycle
from backend.app.services.i5.know05.rag_coherence import (
    audit_rag_coherence,
    invalidate_rag_for_knowledge_unit,
    resolve_ku_rights_state,
)


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _require_065(engine):
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head != "068_i7_wave2_governed_memory_lifecycle":
            pytest.skip(f"alembic head {head} != 065")


def _make_ku(db, *, suffix: str, eligible: bool = True, retracted: bool = False, pub: str = "PUBLISHED"):
    statement = f"know05 remediation fixture {suffix}"
    ku = models.KnowledgeUnit(
        canonical_unit_id=hashlib.sha256(f"c:{suffix}".encode()).hexdigest()[:32],
        immutable_version_id="v1",
        domain="test",
        knowledge_type=KnowledgeType.FACT.value,
        normalized_statement=statement,
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=MedicalSafetyState.UNKNOWN.value,
        conflict_state=ConflictState.NONE.value,
        freshness_state=FreshnessState.CURRENT.value,
        review_state=ReviewState.APPROVED.value,
        publication_state=pub,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.ELIGIBLE.value
        if eligible
        else KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
        provenance_complete=True,
        canonical_hash=hashlib.sha256(statement.encode()).hexdigest(),
        deduplication_key=hashlib.sha256(f"d:{suffix}".encode()).hexdigest(),
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
        retraction_reason="RETRACTED_BY_FIXTURE" if retracted else None,
    )
    db.add(ku)
    db.flush()
    return ku


def _make_source(db, *, key: str, rights_allowed: bool = True):
    gsp = models.GovernedSourceProfile(
        canonical_key=key,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE" if rights_allowed else "NOT_ELIGIBLE",
        operational_status="active",
    )
    db.add(gsp)
    db.flush()
    if rights_allowed:
        ext = models.I5SourceRegistryExtension(
            source_profile_id=gsp.id,
            source_universe="GLOBAL_KNOWLEDGE",
            authority_class="CLINICAL_TRIAL_REGISTRY",
            access_right=RightDecision.ALLOWED.value,
            automation_right=RightDecision.ALLOWED.value,
            tdm_right=RightDecision.ALLOWED.value,
            transform_right=RightDecision.ALLOWED.value,
            retain_raw_right=RightDecision.DENIED.value,
            retain_derived_right=RightDecision.ALLOWED.value,
            redistribution_right=RightDecision.DENIED.value,
            robots_state="ALLOWED",
            processing_permission_mode=ProcessingPermissionMode.METADATA_ABSTRACT_ONLY.value,
        )
    else:
        ext = models.I5SourceRegistryExtension(
            source_profile_id=gsp.id,
            source_universe="GLOBAL_KNOWLEDGE",
            authority_class="CLINICAL_TRIAL_REGISTRY",
            access_right=RightDecision.DENIED.value,
            automation_right=RightDecision.DENIED.value,
            tdm_right=RightDecision.DENIED.value,
            transform_right=RightDecision.DENIED.value,
            retain_raw_right=RightDecision.DENIED.value,
            retain_derived_right=RightDecision.DENIED.value,
            redistribution_right=RightDecision.DENIED.value,
            robots_state="DISALLOWED",
            processing_permission_mode=ProcessingPermissionMode.FULLTEXT_AUTOMATION_BLOCKED.value,
        )
    db.add(ext)
    db.flush()
    return gsp


def _make_prov(db, ku, gsp):
    prov = models.KnowledgeProvenance(
        knowledge_unit_id=ku.id,
        source_profile_id=gsp.id,
        retrieval_method="fixture",
        access_route="TEST",
        content_hash=hashlib.sha256(b"x").hexdigest(),
    )
    db.add(prov)
    db.flush()
    return prov


def _make_kce(db, *, ku=None, immutable_version_id=None, suffix="x"):
    src = models.KnowledgeSource(slug=f"ks-{suffix}", name=f"KS {suffix}")
    db.add(src)
    db.flush()
    doc = models.KnowledgeDocument(source_id=src.id, title=f"Doc {suffix}")
    db.add(doc)
    db.flush()
    chunk = models.KnowledgeChunk(
        document_id=doc.id,
        content=f"chunk {suffix}",
        citation_label=f"cite-{suffix}",
    )
    db.add(chunk)
    db.flush()
    kce = models.KnowledgeChunkEmbedding(
        chunk_id=chunk.id,
        model_identifier="test-model",
        vector_dimension=3,
        content_hash=hashlib.sha256(f"e:{suffix}".encode()).hexdigest(),
        embedding_status="ready",
        embedding_json="[0,0,0]",
        knowledge_unit_id=ku.id if ku is not None else None,
        immutable_version_id=immutable_version_id if immutable_version_id is not None else (
            ku.immutable_version_id if ku is not None else None
        ),
    )
    db.add(kce)
    db.flush()
    return kce


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_nf18_negative_controls_detect_violations():
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # 1. orphan RAG
        _make_kce(db, ku=None, suffix="orphan")
        # 2. KU without provenance + active index
        ku_no_prov = _make_ku(db, suffix="noprov")
        _make_kce(db, ku=ku_no_prov, suffix="noprov")
        # 3. retracted KU still ELIGIBLE with non-retracted index
        ku_ret = _make_ku(db, suffix="ret", retracted=True)
        gsp_ok = _make_source(db, key="know05:nf18:ok")
        _make_prov(db, ku_ret, gsp_ok)
        _make_kce(db, ku=ku_ret, suffix="ret")
        # 4. superseded still eligible
        ku_sup = _make_ku(db, suffix="sup", pub=PublicationState.SUPERSEDED.value)
        _make_prov(db, ku_sup, gsp_ok)
        _make_kce(db, ku=ku_sup, suffix="sup")
        # 5. rights-blocked
        ku_rb = _make_ku(db, suffix="rb")
        gsp_bad = _make_source(db, key="know05:nf18:blocked", rights_allowed=False)
        _make_prov(db, ku_rb, gsp_bad)
        _make_kce(db, ku=ku_rb, suffix="rb")
        # 6. DB-ineligible with active RAG index
        ku_inelig = _make_ku(db, suffix="inelig", eligible=False)
        _make_prov(db, ku_inelig, gsp_ok)
        _make_kce(db, ku=ku_inelig, suffix="inelig")
        # 7. immutable version mismatch
        ku_mm = _make_ku(db, suffix="mm")
        _make_prov(db, ku_mm, gsp_ok)
        _make_kce(db, ku=ku_mm, immutable_version_id="v999", suffix="mm")
        db.flush()

        report = audit_rag_coherence(db)
        assert report.computation_basis == "DB_DERIVED"
        assert report.orphan_rag_record >= 1
        assert report.rag_record_without_provenance >= 1
        assert report.retracted_rag_runtime_eligible >= 1
        assert report.superseded_rag_runtime_eligible >= 1
        assert report.rights_blocked_rag_eligible >= 1
        assert report.rag_eligible_without_runtime_eligible_db >= 1
        assert report.rag_db_identity_mismatch >= 1
        with pytest.raises(AssertionError, match="RAG_ZERO_STATE_VIOLATION"):
            report.assert_zero_states()

        # Remediate retraction → invalidate KCE; KU still marked ELIGIBLE so count may remain
        # until eligibility cleared — prove invalidation stamps index
        n = invalidate_rag_for_knowledge_unit(db, knowledge_unit_id=ku_ret.id, reason="test")
        assert n >= 1
        db.flush()
        after = audit_rag_coherence(db)
        assert after.rag_invalidated_count >= 1
    finally:
        db.rollback()
        db.close()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_nf19_bounded_ingestion_mock_e2e_beyond_ready():
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    from backend.tests._know05_test_fixtures import seed_canonical_source_with_rights

    class _Resp:
        def __init__(self, payload: dict, status=200):
            self.status_code = status
            self.headers = {"Content-Type": "application/json"}
            self.content = json.dumps(payload).encode()

        def json(self):
            return json.loads(self.content.decode())

    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Know05 diabetes canary"},
            "statusModule": {"overallStatus": "RECRUITING"},
        }
    }

    def fake_get(url, headers=None, timeout=None, params=None):
        if "/studies/" in url and "NCT" in url:
            return _Resp(study)
        return _Resp({"totalCount": 1, "studies": [study], "nextPageToken": None})

    try:
        seed_canonical_source_with_rights(db, rights_mode="ALLOWED")
        db.flush()
        result = ingest_clinicaltrials_bounded(
            db,
            mode=Know05Mode.BOUNDED_INGESTION,
            query="diabetes",
            http_get=fake_get,
            max_records=1,
        )
        db.commit()
        assert result.block_reason is None, f"block_reason={result.block_reason!r} status={result.status}"
        assert result.status == "STORED"
        assert result.request_count >= 1
        assert result.bytes_received > 0
        assert result.http_status == 200
        assert result.records_accepted >= 1
        assert result.knowledge_unit_id is not None
        assert result.transient_raw_residue == 0
        assert result.clinical_runtime_eligible is False
        assert result.synthetic_product_rights_source is False
        assert result.status != "READY_FOR_BOUNDED_FETCH"

        ku = db.query(models.KnowledgeUnit).filter_by(id=result.knowledge_unit_id).first()
        assert ku is not None
        assert ku.runtime_eligibility != "ELIGIBLE"
        assert db.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).first()
        rights = resolve_ku_rights_state(db, knowledge_unit_id=ku.id)
        view = derive_ku_availability(
            ku_id=ku.id,
            runtime_eligibility=ku.runtime_eligibility,
            retraction_reason=ku.retraction_reason,
            freshness_state=ku.freshness_state,
            provenance_complete=ku.provenance_complete,
            publication_state=ku.publication_state,
            has_structured_links=True,
            rights_state=rights,
        )
        assert view.runtime_eligible is False
        assert view.rag_eligible is False
    finally:
        db.close()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_nf20_weekly_rehearsal_selection_and_ingestion():
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    class _Resp:
        def __init__(self, payload: dict, status=200):
            self.status_code = status
            self.headers = {"Content-Type": "application/json"}
            self.content = json.dumps(payload).encode()

        def json(self):
            return json.loads(self.content.decode())

    study = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000002", "briefTitle": "Know05 MS canary"},
            "statusModule": {"overallStatus": "COMPLETED"},
        }
    }

    def fake_get(url, headers=None, timeout=None, params=None):
        if "who.int" in str(url):
            html = b'<html><a href="/publications/i/item/9789240000000">g</a></html>'
            r = type("R", (), {})()
            r.status_code = 200
            r.headers = {"Content-Type": "text/html"}
            r.content = html
            return r
        if "/studies/" in str(url):
            return _Resp(study)
        return _Resp({"totalCount": 1, "studies": [study]})

    try:
        for key, name in (
            ("ALS", "Amyotrophic lateral sclerosis"),
            ("MS", "Multiple sclerosis"),
            ("DIABETES", "Diabetes mellitus"),
            ("HYPERTENSION", "Hypertension"),
        ):
            c = db.query(models.I5ClinicalConcept).filter_by(concept_key=key).first()
            if c is None:
                c = models.I5ClinicalConcept(
                    concept_key=key,
                    preferred_name=name,
                    normalized_name=name.lower(),
                    concept_type="DISEASE",
                )
                db.add(c)
                db.flush()
            ensure_dimension(db, "PHARMACOLOGICAL_TREATMENT")
            upsert_coverage_cell(
                db,
                concept_id=c.id,
                dimension_code="PHARMACOLOGICAL_TREATMENT",
                cell_state=CoverageCellState.MISSING.value,
                evidence_class="CLINICAL_TRIALS" if key == "MS" else "GUIDELINE",
                detail="know05-remediation",
            )
        db.flush()

        from backend.tests._know05_test_fixtures import seed_canonical_source_with_rights

        seed_canonical_source_with_rights(db, connector_key="clinicaltrials_gov_api_v2", rights_mode="ALLOWED")
        seed_canonical_source_with_rights(db, connector_key="who_guideline_catalogue", rights_mode="UNKNOWN")
        db.flush()

        result = run_know05_cycle(
            db,
            mode=Know05Mode.BOUNDED_INGESTION,
            window_tag="know05-remediation-e2e",
            persist_ledger=True,
            execute_ingestion=True,
            http_get=fake_get,
        )
        db.commit()
        assert result.source_selections
        assert any(s.get("p0_overlay") for s in result.source_selections)
        # Registry SoT: CT.gov eligible for trial gaps; WHO UNKNOWN never crawl-eligible.
        assert any(
            s.get("selected_connector") == "clinicaltrials_gov_api_v2"
            and s.get("automation_decision") == "AUTOMATION_ALLOWED"
            for s in result.source_selections
        )
        who_sels = [s for s in result.source_selections if s.get("selected_connector") == "who_guideline_catalogue"]
        for s in who_sels:
            assert s.get("automation_decision") == "BLOCKED"
        # Non-P0 hypertension gap remains classifiable via direct selection even if
        # weekly budget truncates prioritized cells to P0-only.
        from backend.app.services.i5.know05.coverage_engine import CoveragePrioritizationItem
        from backend.app.services.i5.know05.source_selection import select_connectors_for_gap

        ht = db.query(models.I5ClinicalConcept).filter_by(concept_key="HYPERTENSION").one()
        ht_sels = select_connectors_for_gap(
            db,
            CoveragePrioritizationItem(
                cell_id=0,
                concept_id=ht.id,
                dimension_code="PHARMACOLOGICAL_TREATMENT",
                evidence_class="GUIDELINE",
                cell_state=CoverageCellState.MISSING.value,
                priority="P1",
                p0_overlay=False,
                gap_key="htn-direct",
            ),
        )
        assert ht_sels
        assert all(s.p0_overlay is False for s in ht_sels)
        assert any(s["status"] in {"STORED", "FETCHED", "BLOCKED"} for s in result.source_results)
        assert "READY_FOR_BOUNDED_FETCH" not in {s["status"] for s in result.source_results}
        assert result.weekly_run_id is not None

        auth = audit_knowledge_authority(db)
        assert auth.duplicate_knowledge_authority == 0
    finally:
        db.close()
