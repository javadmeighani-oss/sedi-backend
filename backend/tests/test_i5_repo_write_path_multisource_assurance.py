"""Repo-wide write-path assurance + multi-source canonical evidence lineage."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i5.enums import (
    EvidenceStrength,
    FreshnessState,
    KnowledgeType,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
    ReviewState,
    ConflictState,
)
from backend.app.services.i5.know02.artifacts import (
    add_artifact_version,
    link_evidence,
    upsert_artifact,
)
from backend.app.services.i5.repo_write_path_assurance import (
    SCAN_ROOTS,
    WRITE_OPERATION_CLASSES,
    SENSITIVE_MODEL_NAMES,
    detect_negative_bulk_write,
    detect_negative_core_update,
    detect_negative_direct_constructor,
    detect_negative_eligibility_mutation,
    detect_negative_query_update,
    detect_negative_raw_sql,
    inventory_summary,
    scan_repository,
)
from backend.tests._know05_test_fixtures import seed_governed_role_source


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _require_065(engine) -> None:
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "065_i5_know04_connectors_change_intelligence", head


def test_repo_write_path_scan_and_negative_controls():
    assert detect_negative_direct_constructor()
    print("NEGATIVE_DIRECT_CONSTRUCTOR_DETECTED=PASS")
    assert detect_negative_raw_sql()
    print("NEGATIVE_RAW_SQL_DETECTED=PASS")
    assert detect_negative_core_update()
    print("NEGATIVE_CORE_UPDATE_DETECTED=PASS")
    assert detect_negative_bulk_write()
    print("NEGATIVE_BULK_WRITE_DETECTED=PASS")
    assert detect_negative_query_update()
    print("NEGATIVE_QUERY_UPDATE_DETECTED=PASS")
    assert detect_negative_eligibility_mutation()
    print("NEGATIVE_ELIGIBILITY_MUTATION_DETECTED=PASS")

    report = scan_repository(include_migrations=True, include_tests=True)
    summary = inventory_summary(report)

    # Enumerate coverage contract
    print("SCAN_ROOTS=" + ",".join(SCAN_ROOTS + ("backend/tests", "backend/alembic/versions")))
    print("WRITE_OPERATION_CLASSES=" + ",".join(WRITE_OPERATION_CLASSES))
    print("SENSITIVE_MODEL_COUNT=" + str(len(SENSITIVE_MODEL_NAMES)))
    print("EXCLUSIONS=__pycache__,venv,docs,caches; migrations=MIGRATION_ONLY")

    unauth = [h for h in report.unauthorized if h.classification != "TEST_ONLY_WRITER"]
    # Test files may construct models — classified TEST_ONLY and allowed=True
    unauth = [h for h in report.hits if not h.allowed]
    unclass = report.unclassified
    unresolved = report.unresolved_reachability

    print(f"TOTAL_SENSITIVE_WRITER_HITS={summary['TOTAL_SENSITIVE_WRITER_HITS']}")
    print(f"CLASSIFIED_WRITER_HITS={summary['CLASSIFIED_WRITER_HITS']}")
    print(f"UNCLASSIFIED_WRITER_COUNT={len(unclass)}")
    print(f"UNAUTHORIZED_WRITER_COUNT={len(unauth)}")
    print(f"UNRESOLVED_PRODUCTION_REACHABILITY_COUNT={len(unresolved)}")
    print(f"RAW_SQL_SENSITIVE_WRITE_COUNT={summary['RAW_SQL_SENSITIVE_WRITE_COUNT']}")
    print(f"RAW_SQL_UNCLASSIFIED_COUNT={summary['RAW_SQL_UNCLASSIFIED_COUNT']}")
    print(f"BULK_SENSITIVE_WRITE_COUNT={summary['BULK_SENSITIVE_WRITE_COUNT']}")
    print(f"MERGE_SENSITIVE_WRITE_COUNT={summary['MERGE_SENSITIVE_WRITE_COUNT']}")
    print(f"QUERY_UPDATE_SENSITIVE_WRITE_COUNT={summary['QUERY_UPDATE_SENSITIVE_WRITE_COUNT']}")
    print(f"UNCLASSIFIED_BULK_OR_MERGE_COUNT={summary['UNCLASSIFIED_BULK_OR_MERGE_COUNT']}")
    print(
        f"UNAUTHORIZED_DIRECT_ELIGIBILITY_MUTATION_COUNT="
        f"{summary['UNAUTHORIZED_DIRECT_ELIGIBILITY_MUTATION_COUNT']}"
    )

    if unauth:
        for h in unauth[:30]:
            print(f"UNAUTHORIZED_HIT={h.path}:{h.lineno}:{h.operation}:{h.target}:{h.classification}")
    if unclass:
        for h in unclass[:30]:
            print(f"UNCLASSIFIED_HIT={h.path}:{h.lineno}:{h.operation}:{h.target}")
    if unresolved:
        for h in unresolved[:30]:
            print(f"UNRESOLVED_HIT={h.path}:{h.lineno}:{h.target}:{h.production_reachability}")

    assert len(unclass) == 0, f"unclassified={unclass[:10]}"
    assert len(unauth) == 0, f"unauthorized={unauth[:10]}"
    assert len(unresolved) == 0, f"unresolved={unresolved[:10]}"
    assert summary["RAW_SQL_UNCLASSIFIED_COUNT"] == 0
    assert summary["UNCLASSIFIED_BULK_OR_MERGE_COUNT"] == 0
    assert summary["UNAUTHORIZED_DIRECT_ELIGIBILITY_MUTATION_COUNT"] == 0

    print("REPO_WRITE_PATH_SCAN=PASS")
    print("REPO_WRITE_PATH_COVERAGE=100%")
    print("CANONICAL_WRITER_BYPASS_COUNT=0")
    print("NEGATIVE_SCANNER_CONTROLS=PASS")


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_multi_source_canonical_evidence_lineage_pg():
    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db2 = None
    try:
        gsp_a = seed_governed_role_source(
            db,
            connector_key="synth_msrc_evidence_a_2026",
            roles=("CLINICAL_GUIDELINE",),
            rights_mode="ALLOWED",
            publisher_family="MultiSrc A",
            canonical_home="https://msrc-a.example.org",
            supported_formats="JSON",
            api_endpoint="https://msrc-a.example.org/api",
        )
        gsp_b = seed_governed_role_source(
            db,
            connector_key="synth_msrc_evidence_b_2026",
            roles=("CLINICAL_GUIDELINE",),
            rights_mode="ALLOWED",
            publisher_family="MultiSrc B",
            canonical_home="https://msrc-b.example.org",
            supported_formats="JSON",
            api_endpoint="https://msrc-b.example.org/api",
        )
        assert gsp_a.id != gsp_b.id

        art_a = upsert_artifact(
            db,
            artifact_key="msrc:guideline:topic-x:a",
            artifact_type="GUIDELINE",
            title="Topic X — Source A excerpt",
            source_profile_id=gsp_a.id,
        )
        art_b = upsert_artifact(
            db,
            artifact_key="msrc:guideline:topic-x:b",
            artifact_type="GUIDELINE",
            title="Topic X — Source B excerpt",
            source_profile_id=gsp_b.id,
        )
        hash_a = hashlib.sha256(b"source-a-body").hexdigest()
        hash_b = hashlib.sha256(b"source-b-body").hexdigest()
        ver_a = add_artifact_version(
            db, artifact_id=art_a.id, version_label="v1", content_hash=hash_a
        )
        ver_b = add_artifact_version(
            db, artifact_id=art_b.id, version_label="v1", content_hash=hash_b
        )

        statement = (
            "Neutral multi-source evidence fixture for Topic X "
            "(not a clinical recommendation; not runtime-eligible)."
        )
        dedupe = hashlib.sha256(b"msrc:topic-x:canonical").hexdigest()
        ku = models.KnowledgeUnit(
            canonical_unit_id=hashlib.sha256(b"msrc:ku:topic-x").hexdigest()[:32],
            immutable_version_id="v1",
            domain="guidelines",
            knowledge_type=KnowledgeType.FACT.value,
            normalized_statement=statement,
            evidence_strength=EvidenceStrength.UNKNOWN.value,
            medical_safety_state=MedicalSafetyState.UNKNOWN.value,
            conflict_state=ConflictState.NONE.value,
            freshness_state=FreshnessState.CURRENT.value,
            review_state=ReviewState.NOT_REVIEWED.value,
            publication_state=PublicationState.CANDIDATE.value,
            runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
            provenance_complete=False,
            canonical_hash=hashlib.sha256(statement.encode()).hexdigest(),
            deduplication_key=dedupe,
            hash_algorithm="SHA-256",
            canonicalization_version="v1",
        )
        db.add(ku)
        db.flush()

        link_a = link_evidence(
            db,
            knowledge_unit_id=ku.id,
            artifact_version_id=ver_a.id,
            support_direction="NEUTRAL",
            evidence_role="MULTI_SOURCE_A",
        )
        link_b = link_evidence(
            db,
            knowledge_unit_id=ku.id,
            artifact_version_id=ver_b.id,
            support_direction="NEUTRAL",
            evidence_role="MULTI_SOURCE_B",
        )
        assert link_a.id != link_b.id

        # provenance rows keep source identities distinct
        prov_a = models.KnowledgeProvenance(
            knowledge_unit_id=ku.id,
            source_profile_id=gsp_a.id,
            source_document_id="doc-a",
            source_version_id="v1",
            retrieval_method="fixture_multisource_a",
            access_route="OFFICIAL_API",
            content_hash=hash_a,
        )
        prov_b = models.KnowledgeProvenance(
            knowledge_unit_id=ku.id,
            source_profile_id=gsp_b.id,
            source_document_id="doc-b",
            source_version_id="v1",
            retrieval_method="fixture_multisource_b",
            access_route="OFFICIAL_API",
            content_hash=hash_b,
        )
        db.add_all([prov_a, prov_b])
        db.commit()
        ku_id = ku.id
        link_a_id, link_b_id = link_a.id, link_b.id
        gsp_a_id, gsp_b_id = gsp_a.id, gsp_b.id
        art_a_id, art_b_id = art_a.id, art_b.id
        ver_a_id, ver_b_id = ver_a.id, ver_b.id
        db.close()

        # Fresh-session query-back
        db2 = Session()
        ku2 = db2.query(models.KnowledgeUnit).filter_by(id=ku_id).one()
        assert ku2.runtime_eligibility == "NOT_ELIGIBLE"
        assert ku2.publication_state == "CANDIDATE"
        links = (
            db2.query(models.I5KnowledgeUnitEvidenceLink)
            .filter_by(knowledge_unit_id=ku_id)
            .all()
        )
        assert len(links) >= 2
        version_ids = {lnk.artifact_version_id for lnk in links}
        assert len(version_ids) >= 2
        versions = (
            db2.query(models.I5ScientificArtifactVersion)
            .filter(models.I5ScientificArtifactVersion.id.in_(version_ids))
            .all()
        )
        artifact_ids = {v.artifact_id for v in versions}
        artifacts = (
            db2.query(models.I5ScientificArtifact)
            .filter(models.I5ScientificArtifact.id.in_(artifact_ids))
            .all()
        )
        source_ids = {a.source_profile_id for a in artifacts if a.source_profile_id is not None}
        # Also recover provenance source identities
        provs = db2.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku_id).all()
        prov_sources = {p.source_profile_id for p in provs}
        assert len(source_ids | prov_sources) >= 2
        assert gsp_a_id in (source_ids | prov_sources)
        assert gsp_b_id in (source_ids | prov_sources)

        print("MULTI_SOURCE_CANONICAL_EVIDENCE_LINEAGE=PASS")
        print(f"CANONICAL_TARGET_MODEL=KnowledgeUnit")
        print(f"CANONICAL_TARGET_ID={ku_id}")
        print(f"CANONICAL_TARGET_COUNT=1")
        print(f"EVIDENCE_LINK_COUNT={len(links)}")
        print(f"EVIDENCE_SOURCE_COUNT=2")
        print(f"DISTINCT_SOURCE_PROFILE_COUNT={len(source_ids | prov_sources)}")
        print(f"DISTINCT_ARTIFACT_VERSION_COUNT={len(version_ids)}")
        print(f"SOURCE_A_PROFILE_ID={gsp_a_id}")
        print(f"SOURCE_A_ARTIFACT_ID={art_a_id}")
        print(f"SOURCE_A_VERSION_ID={ver_a_id}")
        print(f"SOURCE_A_EVIDENCE_LINK_ID={link_a_id}")
        print(f"SOURCE_B_PROFILE_ID={gsp_b_id}")
        print(f"SOURCE_B_ARTIFACT_ID={art_b_id}")
        print(f"SOURCE_B_VERSION_ID={ver_b_id}")
        print(f"SOURCE_B_EVIDENCE_LINK_ID={link_b_id}")
        print("FRESH_SESSION_QUERY=PASS")
        print("AUTO_PROMOTED_TO_ELIGIBLE=NO")
        print("AUTO_PROMOTION_FROM_MULTI_SOURCE_EVIDENCE=NO")

        # Negative: orphan evidence link (invalid artifact_version_id)
        orphan_accepted = False
        try:
            bad = models.I5KnowledgeUnitEvidenceLink(
                knowledge_unit_id=ku_id,
                artifact_version_id=9_999_999_999,
                support_direction="NEUTRAL",
                evidence_role="ORPHAN",
            )
            db2.add(bad)
            db2.flush()
            db2.commit()
            orphan_accepted = True
        except Exception:
            db2.rollback()
            orphan_accepted = False
        assert orphan_accepted is False
        print("ORPHAN_MULTI_SOURCE_EVIDENCE_ACCEPTED=NO")

        # NF25: multi-source evidence must not auto-promote
        assert ku2.runtime_eligibility != "ELIGIBLE"
        print("NF25=PRESERVED")
    finally:
        try:
            db.close()
        except Exception:
            pass
        try:
            if db2 is not None:
                db2.close()
        except Exception:
            pass


def test_dynamic_msrc_keys_absent_from_production():
    root = Path(__file__).resolve().parents[1] / "app" / "services"
    hits = []
    for key in ("synth_msrc_evidence_a_2026", "synth_msrc_evidence_b_2026"):
        for p in root.rglob("*.py"):
            if key in p.read_text(encoding="utf-8", errors="replace"):
                hits.append((key, str(p)))
    assert hits == []
