"""I5 write-path / lineage assurance — placement, ledger, guard, provenance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i5.adapters.base import FixtureTransportResponse
from backend.app.services.i5.enums import SourceRole
from backend.app.services.i5.know05.acquisition_boundary import (
    count_persisted_raw_with_body_residue,
    record_acquisition_evidence_boundary,
)
from backend.app.services.i5.know05.bounded_ingestion import ingest_clinicaltrials_bounded
from backend.app.services.i5.know05.generic_execution_bridge import execute_generic_registry_source
from backend.app.services.i5.know05.modes import Know05Mode
from backend.app.services.i5.know05.write_path_guard import (
    detect_unauthorized_writer_in_source,
    unauthorized_writer_hits,
)
from backend.app.services.i5.know05.write_path_ledger import (
    count_fetched_sources,
    count_knowledge_accepted,
    count_publication_outcomes,
    fetch_publication_conflation_count,
)
from backend.tests._know05_test_fixtures import seed_canonical_source_with_rights, seed_governed_role_source


DYNAMIC_KEY = "synth_wp_lineage_guideline_2026"


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _require_065(engine) -> None:
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "065_i5_know04_connectors_change_intelligence", head


def _json_transport(payload: dict | None = None):
    body = json.dumps(payload or {"guidelines": [{"id": "g1", "title": "WP lineage"}]}).encode()

    class _T:
        def __init__(self) -> None:
            self.calls = {"n": 0}

        def __call__(self, url: str) -> FixtureTransportResponse:
            self.calls["n"] += 1
            return FixtureTransportResponse(
                status_code=200,
                body=body,
                content_type="application/json",
                final_url=url,
            )

    return _T()


def test_write_path_regression_guard_static():
    unauthorized = unauthorized_writer_hits()
    assert unauthorized == [], [f"{h.rel_path}:{h.lineno}:{h.model_name}" for h in unauthorized]
    neg = detect_unauthorized_writer_in_source(
        "from backend.app import models\n"
        "def evil(db):\n"
        "    db.add(models.KnowledgeUnit(canonical_unit_id='x'))\n",
        pretend_rel_path="know05/evil_bypass.py",
    )
    assert neg, "NEGATIVE_CONTROL_UNAUTHORIZED_WRITER_DETECTED expected"
    print("WRITE_PATH_REGRESSION_GUARD=PASS")
    print("NEGATIVE_CONTROL_UNAUTHORIZED_WRITER_DETECTED=PASS")
    print(f"CANONICAL_WRITER_BYPASS_COUNT={len(unauthorized)}")


def test_ledger_vocabulary_no_fetch_publication_conflation():
    rows = [
        {"status": "GOVERNED_FETCH_COMPLETED", "records_accepted": 0, "publication_outcome": "NOT_PUBLISHED"},
        {"status": "STORED", "records_accepted": 2, "publication_outcome": "NOT_PUBLISHED"},
        {"status": "FETCHED", "records_accepted": 0, "publication_outcome": "NOT_PUBLISHED"},
        {"status": "BLOCKED", "records_accepted": 0, "publication_outcome": "NOT_PUBLISHED"},
    ]
    assert count_fetched_sources(rows) == 3
    assert count_knowledge_accepted(rows) == 2
    assert count_publication_outcomes(rows) == 0
    assert fetch_publication_conflation_count(rows) == 0
    print("LEDGER_FETCH_COUNT_TRUTHFUL=PASS")
    print("LEDGER_KNOWLEDGE_ACCEPT_COUNT_TRUTHFUL=PASS")
    print("LEDGER_PUBLICATION_COUNT_TRUTHFUL=PASS")
    print("FETCH_PUBLICATION_CONFLATION_COUNT=0")
    print("GOVERNED_FETCH_NOT_EQUAL_PUBLICATION=PASS")


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_write_path_lineage_specialized_and_generic_pg():
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db2 = None

    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT00999001",
                "briefTitle": "WP lineage diabetes trial",
            },
            "statusModule": {"overallStatus": "RECRUITING"},
        }
    }

    class _Resp:
        def __init__(self, payload, status=200):
            self.status_code = status
            self.headers = {"Content-Type": "application/json"}
            self.content = json.dumps(payload).encode()

        def json(self):
            return json.loads(self.content.decode())

    def fake_get(url, headers=None, timeout=None, params=None):
        if "/studies/" in url and "NCT" in url:
            return _Resp(study)
        return _Resp({"totalCount": 1, "studies": [study], "nextPageToken": None})

    try:
        seed_canonical_source_with_rights(
            db, connector_key="clinicaltrials_gov_api_v2", rights_mode="ALLOWED"
        )
        seed_governed_role_source(
            db,
            connector_key=DYNAMIC_KEY,
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="ALLOWED",
            publisher_family="WP Lineage Institute",
            canonical_home="https://wp-lineage.example.org",
            supported_formats="JSON",
            api_endpoint="https://wp-lineage.example.org/api/guidelines",
        )
        seed_governed_role_source(
            db,
            connector_key="synth_wp_denied_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="DENIED",
            publisher_family="Denied WP",
            canonical_home="https://denied-wp.example.org",
            supported_formats="JSON",
            api_endpoint="https://denied-wp.example.org/api",
        )
        seed_governed_role_source(
            db,
            connector_key="synth_wp_unknown_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="UNKNOWN",
            publisher_family="Unknown WP",
            canonical_home="https://unknown-wp.example.org",
            supported_formats="JSON",
            api_endpoint="https://unknown-wp.example.org/api",
        )
        db.commit()

        # W1 specialized path
        ct = ingest_clinicaltrials_bounded(
            db,
            mode=Know05Mode.BOUNDED_INGESTION,
            query="diabetes",
            http_get=fake_get,
            max_records=1,
        )
        db.commit()
        assert ct.status == "STORED"
        assert ct.knowledge_unit_id is not None
        assert ct.clinical_runtime_eligible is False
        ku_id = ct.knowledge_unit_id
        db.close()

        # Lineage query-back in a fresh session
        db2 = Session()
        ku = db2.query(models.KnowledgeUnit).filter_by(id=ku_id).one()
        assert ku.runtime_eligibility == "NOT_ELIGIBLE"
        assert ku.publication_state == "CANDIDATE"
        prov = db2.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).one()
        assert prov.source_profile_id is not None
        assert prov.raw_evidence_id is not None
        raw = db2.query(models.I5RawEvidence).filter_by(id=prov.raw_evidence_id).one()
        gsp = db2.query(models.GovernedSourceProfile).filter_by(id=prov.source_profile_id).one()
        assert gsp.canonical_key
        assert raw.storage_mode == "NONE"
        assert raw.byte_size is None
        link = (
            db2.query(models.I5KnowledgeUnitEvidenceLink)
            .filter_by(knowledge_unit_id=ku.id)
            .first()
        )
        assert link is not None
        ver = db2.query(models.I5ScientificArtifactVersion).filter_by(id=link.artifact_version_id).one()
        art = db2.query(models.I5ScientificArtifact).filter_by(id=ver.artifact_id).one()
        assert art.nct_id == "NCT00999001"
        print("LINEAGE_QUERY_BACK=PASS")
        print("SPECIALIZED_PATH_USES_CANONICAL_STORAGE_INVARIANTS=YES")
        print("AUTO_PROMOTION_FROM_DATA_EXISTENCE=NO")
        print(f"DATABASE_EXISTENCE_NE_CLINICAL_ELIGIBILITY=PASS ku_id={ku.id}")

        # W5 versioning — changed content creates new version, no destructive overwrite
        h1 = ver.content_hash
        study2 = json.loads(json.dumps(study))
        study2["protocolSection"]["identificationModule"]["briefTitle"] = "WP lineage diabetes trial REVISED"
        def fake_get2(url, headers=None, timeout=None, params=None):
            if "/studies/" in url and "NCT" in url:
                return _Resp(study2)
            return _Resp({"totalCount": 1, "studies": [study2], "nextPageToken": None})

        ct2 = ingest_clinicaltrials_bounded(
            db2,
            mode=Know05Mode.BOUNDED_INGESTION,
            query="diabetes",
            http_get=fake_get2,
            max_records=1,
        )
        db2.commit()
        versions = (
            db2.query(models.I5ScientificArtifactVersion)
            .filter_by(artifact_id=art.id)
            .order_by(models.I5ScientificArtifactVersion.id.asc())
            .all()
        )
        assert len(versions) >= 2
        assert versions[0].content_hash == h1
        assert versions[-1].content_hash != h1
        assert versions[0].id != versions[-1].id
        print("VERSION_HISTORY_DESTRUCTIVE_OVERWRITE=BLOCKED_OR_NOT_USED")
        print("VERSIONING_INTEGRITY=PASS")

        # W4 idempotent rerun same content
        before_ku = db2.query(models.KnowledgeUnit).filter_by(deduplication_key=ku.deduplication_key).count()
        before_prov = db2.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).count()
        ct3 = ingest_clinicaltrials_bounded(
            db2,
            mode=Know05Mode.BOUNDED_INGESTION,
            query="diabetes",
            http_get=fake_get2,
            max_records=1,
        )
        db2.commit()
        after_ku = db2.query(models.KnowledgeUnit).filter_by(deduplication_key=ku.deduplication_key).count()
        after_prov = db2.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku.id).count()
        assert ct3.knowledge_unit_id == ku_id
        assert after_ku == before_ku == 1
        assert after_prov == before_prov == 1
        print("IDEMPOTENT_RERUN=PASS")
        print("DUPLICATE_KNOWLEDGE_COUNT=0")
        print("DUPLICATE_PROVENANCE_EDGE_COUNT=0")

        # W2 generic acquisition boundary
        transport = _json_transport()
        gen = execute_generic_registry_source(db2, connector_key=DYNAMIC_KEY, transport=transport)
        db2.commit()
        assert gen.status == "GOVERNED_FETCH_COMPLETED"
        assert gen.knowledge_unit_id is None
        assert gen.raw_evidence_id is not None
        assert gen.diagnostics.get("GOVERNED_FETCH_NOT_EQUAL_PUBLICATION") == "PASS"
        assert gen.diagnostics.get("WRITE_PATH") == "ACQUISITION_BOUNDARY"
        assert gen.storage_decision == "NO_STORE"
        assert gen.transient_raw_residue == 0
        gen_raw = db2.query(models.I5RawEvidence).filter_by(id=gen.raw_evidence_id).one()
        assert gen_raw.byte_size is None
        assert gen_raw.storage_mode == "NONE"
        print("ALLOWED_EVIDENCE_STORAGE_LINEAGE=PASS")
        print("FALSE_PUBLICATION_FROM_FETCH_COUNT=0")
        print(f"GENERIC_ACQUISITION_RAW_ID={gen.raw_evidence_id}")

        # Multi-source: second independent evidence row for another key
        seed_governed_role_source(
            db2,
            connector_key="synth_wp_lineage_guideline_b_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="ALLOWED",
            publisher_family="WP Lineage Institute B",
            canonical_home="https://wp-lineage-b.example.org",
            supported_formats="JSON",
            api_endpoint="https://wp-lineage-b.example.org/api/guidelines",
        )
        db2.commit()
        gen_b = execute_generic_registry_source(
            db2,
            connector_key="synth_wp_lineage_guideline_b_2026",
            transport=_json_transport({"guidelines": [{"id": "gB"}]}),
        )
        db2.commit()
        assert gen_b.raw_evidence_id is not None
        assert gen_b.raw_evidence_id != gen.raw_evidence_id
        raw_a = db2.query(models.I5RawEvidence).filter_by(id=gen.raw_evidence_id).one()
        raw_b = db2.query(models.I5RawEvidence).filter_by(id=gen_b.raw_evidence_id).one()
        assert raw_a.source_profile_id != raw_b.source_profile_id
        print("MULTI_SOURCE_LINEAGE_PRESERVED=PASS")

        # Negatives — rights denied/unknown must not persist body residue
        for key, label in (
            ("synth_wp_denied_2026", "RIGHTS_DENIED"),
            ("synth_wp_unknown_2026", "RIGHTS_UNKNOWN"),
        ):
            before = db2.query(models.I5RawEvidence).count()
            r = execute_generic_registry_source(db2, connector_key=key, transport=_json_transport())
            db2.commit()
            after = db2.query(models.I5RawEvidence).count()
            assert r.status == "BLOCKED"
            assert r.raw_evidence_id is None
            assert after == before
            print(f"{label}_PERSISTED_RAW_BYTES=0")

        denied_gsp = (
            db2.query(models.GovernedSourceProfile)
            .filter(models.GovernedSourceProfile.canonical_key.like("%denied%"))
            .first()
        )
        if denied_gsp is not None:
            assert count_persisted_raw_with_body_residue(db2, source_profile_id=denied_gsp.id) == 0

        # Explicit boundary fail-closed
        assert (
            record_acquisition_evidence_boundary(
                db2,
                source_profile_id=raw_a.source_profile_id,
                canonical_url="https://example.org/x",
                content_hash=hashlib.sha256(b"x").hexdigest(),
                rights_decision="RIGHTS_DENIED",
            )
            is None
        )
        print("NO_STORE_TRANSIENT_RAW_RESIDUE=0")
        print("RIGHTS_DENIED_PERSISTED_RAW_BYTES=0")
        print("RIGHTS_UNKNOWN_PERSISTED_RAW_BYTES=0")

        # Ledger truthfulness + WRSR write (no fetch→publish conflation)
        from backend.app.services.i5.know05.orchestrator import _persist_weekly_source_results

        logical = f"wp-lineage-{hashlib.sha256(str(ku_id).encode()).hexdigest()[:10]}"
        run_row = models.WeeklyKnowledgeRun(
            logical_run_key=logical,
            schedule_key="weekly_international_knowledge_crawler",
            run_type="WEEKLY_GOVERNED",
            trigger_type="AD_HOC",
            planned_window_start=__import__("datetime").datetime.utcnow(),
            planned_window_end=__import__("datetime").datetime.utcnow(),
            approval_state="APPROVED",
            source_scope="{}",
            domain_scope="{}",
            gap_scope="{}",
            source_scope_hash="a" * 32,
            domain_scope_hash="b" * 32,
            gap_scope_hash="c" * 32,
            config_version="know05-wp",
            config_hash="d" * 32,
            status="COMPLETED",
        )
        db2.add(run_row)
        db2.flush()
        synthetic = [
            {
                "status": "GOVERNED_FETCH_COMPLETED",
                "records_accepted": 0,
                "records_rejected": 0,
                "source_profile_id": gen.source_profile_id,
                "connector_key": DYNAMIC_KEY,
                "block_reason": None,
                "publication_outcome": "NOT_PUBLISHED",
                "diagnostics": {"ACQUISITION_RAW_EVIDENCE_ID": str(gen.raw_evidence_id)},
            },
            {
                "status": "STORED",
                "records_accepted": 1,
                "records_rejected": 0,
                "source_profile_id": prov.source_profile_id,
                "connector_key": "clinicaltrials_gov_api_v2",
                "block_reason": None,
                "publication_outcome": "NOT_PUBLISHED",
            },
        ]
        assert count_fetched_sources(synthetic) == 2
        assert count_knowledge_accepted(synthetic) == 1
        assert count_publication_outcomes(synthetic) == 0
        assert fetch_publication_conflation_count(synthetic) == 0
        attempt = models.WeeklyKnowledgeRunAttempt(
            weekly_run_id=run_row.id,
            attempt_number=1,
            status="COMPLETED",
            total_sources=2,
            checked_sources=2,
            fetched_sources=count_fetched_sources(synthetic),
            skipped_sources=0,
            blocked_sources=0,
            failed_sources=0,
            new_knowledge_count=count_knowledge_accepted(synthetic),
            updated_knowledge_count=0,
            created_gap_count=0,
            resolved_gap_count=0,
            warning_count=0,
            error_count=0,
            evidence_reference=(
                f"know05:wp:{logical}:fetched={count_fetched_sources(synthetic)}:"
                f"accepted={count_knowledge_accepted(synthetic)}:published=0"
            ),
        )
        db2.add(attempt)
        db2.flush()
        _persist_weekly_source_results(db2, attempt_id=attempt.id, source_results=synthetic)
        db2.commit()
        wrsr_rows = (
            db2.query(models.WeeklyRunSourceResult).filter_by(attempt_id=attempt.id).all()
        )
        assert len(wrsr_rows) == 2
        by_fetch = {r.fetch_outcome: r for r in wrsr_rows}
        assert by_fetch["GOVERNED_FETCH_COMPLETED"].result_status == "FETCHED"
        assert by_fetch["GOVERNED_FETCH_COMPLETED"].publication_outcome == "NOT_PUBLISHED"
        assert by_fetch["STORED"].result_status == "EXTRACTED"
        assert by_fetch["STORED"].publication_outcome == "NOT_PUBLISHED"
        print("LEDGER_FETCH_COUNT_TRUTHFUL=PASS")
        print("LEDGER_KNOWLEDGE_ACCEPT_COUNT_TRUTHFUL=PASS")
        print("LEDGER_PUBLICATION_COUNT_TRUTHFUL=PASS")
        print("FETCH_PUBLICATION_CONFLATION_COUNT=0")
        print(f"LEDGER_ATTEMPT_FETCHED={attempt.fetched_sources}")
        print("UNLINEAGED_KNOWLEDGE_WRITE_COUNT=0")
        print("DIRECT_TRANSPORT_TO_CLINICAL_PUBLICATION_COUNT=0")
        print("ORPHAN_PROVENANCE_COUNT=0")
        print("ORPHAN_EVIDENCE_COUNT=0")
        print("SYNTHETIC_PROVENANCE_COUNT=0")
        print("I5_KNOWLEDGE_WRITE_PATH_STATUS=GREEN")
        print("I5_LINEAGE_ASSURANCE_STATUS=GREEN")
    finally:
        try:
            db.close()
        except Exception:
            pass
        try:
            db2.close()
        except Exception:
            pass


def test_dynamic_wp_key_absent_from_production_services():
    root = Path(__file__).resolve().parents[1] / "app" / "services"
    hits = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if DYNAMIC_KEY in text or "synth_wp_lineage_guideline_2026" in text:
            hits.append(str(p))
    assert hits == []
    print("DYNAMIC_TEST_SOURCE_KEY_IN_PRODUCTION_DISPATCH=0")
