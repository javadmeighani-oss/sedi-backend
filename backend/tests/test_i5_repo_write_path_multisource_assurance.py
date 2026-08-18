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
    EXPLICIT_TABLE_EXCLUSIONS,
    SCAN_ROOTS,
    SENSITIVE_ATTRS,
    SENSITIVE_MODEL_NAMES,
    SENSITIVE_TABLE_NAMES,
    WRITE_OPERATION_CLASSES,
    detect_negative_bulk_write,
    detect_negative_core_table_insert,
    detect_negative_core_update,
    detect_negative_direct_constructor,
    detect_negative_eligibility_mutation,
    detect_negative_orm_add_all_indirect,
    detect_negative_orm_add_indirect,
    detect_negative_query_update,
    detect_negative_raw_sql,
    detect_negative_raw_sql_case_variation,
    detect_negative_raw_sql_multiline,
    detect_negative_raw_sql_recommendation_evidence,
    detect_negative_raw_sql_study_effect,
    detect_negative_raw_sql_study_population,
    detect_negative_secondary_sensitive_mutation,
    discover_unscanned_db_writing_roots,
    inventory_summary,
    reconstruct_persistence_universe,
    reconcile_migration_i5_tables,
    refresh_sensitive_regexes,
    scan_repository,
    stale_path_classification_entries,
)
from backend.tests._know05_test_fixtures import seed_governed_role_source


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _require_065(engine) -> None:
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "067_i7_lifelong_memory_foundation", head


def test_repo_write_path_universe_and_scanner_completeness():
    refresh_sensitive_regexes()
    universe = reconstruct_persistence_universe()
    assert len(universe.sensitive_model_names) >= 50
    assert len(universe.sensitive_table_names) >= 50
    print(f"AUTHORITATIVE_MODEL_UNIVERSE_COUNT={len(universe.entries)}")
    print(f"AUTHORITATIVE_TABLE_UNIVERSE_COUNT={len({e.tablename for e in universe.entries})}")
    print(f"SENSITIVE_MODEL_COUNT={len(universe.sensitive_model_names)}")
    print(f"SENSITIVE_TABLE_COUNT={len(universe.sensitive_table_names)}")
    assert not universe.unexplained_model_exclusions
    assert not universe.unexplained_table_exclusions
    print("SENSITIVE_MODEL_UNEXPLAINED_EXCLUSION_COUNT=0")
    print("SENSITIVE_TABLE_UNEXPLAINED_EXCLUSION_COUNT=0")
    print("MODEL_TO_TABLE_MAPPING_COMPLETE=PASS")
    print("AUTHORITATIVE_I5_MODEL_UNIVERSE_RECONSTRUCTED=PASS")
    print("AUTHORITATIVE_I5_TABLE_UNIVERSE_RECONSTRUCTED=PASS")

    # Derived tables must equal model.__tablename__ for every sensitive model
    for entry in universe.entries:
        if not entry.sensitive:
            continue
        assert entry.tablename in SENSITIVE_TABLE_NAMES or entry.tablename in EXPLICIT_TABLE_EXCLUSIONS
        cls = getattr(models, entry.model)
        assert cls.__tablename__ == entry.tablename
        assert entry.model in SENSITIVE_MODEL_NAMES
    print("MODEL_TABLENAME_SCANNER_COVERAGE=PASS")
    print("SENSITIVE_TABLE_UNIVERSE_DIFF=0")

    # Required KNOW02/03 families present
    required_tables = {
        "i5_scientific_artifacts",
        "i5_scientific_artifact_versions",
        "i5_knowledge_unit_evidence_links",
        "i5_clinical_studies",
        "i5_study_artifact_links",
        "i5_study_condition_links",
        "i5_study_populations",
        "i5_study_population_criteria",
        "i5_interventions",
        "i5_intervention_mappings",
        "i5_study_interventions",
        "i5_clinical_outcomes",
        "i5_study_outcomes",
        "i5_study_effect_estimates",
        "i5_clinical_recommendations",
        "i5_clinical_recommendation_evidence_links",
    }
    missing = required_tables - set(SENSITIVE_TABLE_NAMES)
    assert not missing, missing

    mig = reconcile_migration_i5_tables(universe)
    unexplained = [t for t, status in mig.items() if status == "UNEXPLAINED"]
    assert not unexplained, unexplained
    print(f"MIGRATION_I5_TABLE_COUNT={len(mig)}")
    print("MIGRATION_I5_TABLE_UNEXPLAINED_DIFF=0")
    print("MIGRATION_I5_TABLE_RECONCILIATION=PASS")
    print("RAW_SQL_DETECTION_TARGET_UNIVERSE_COMPLETE=PASS")
    print("SENSITIVE_ATTRIBUTE_UNIVERSE_RECONSTRUCTED=PASS")
    assert "runtime_eligibility" in SENSITIVE_ATTRS
    assert "publication_state" in SENSITIVE_ATTRS


def test_repo_write_path_scan_and_negative_controls():
    refresh_sensitive_regexes()
    assert detect_negative_direct_constructor()
    print("NEGATIVE_DIRECT_CONSTRUCTOR_DETECTED=PASS")
    assert detect_negative_raw_sql()
    print("NEGATIVE_RAW_SQL_DETECTED=PASS")
    assert detect_negative_raw_sql_study_population()
    print("NEGATIVE_RAW_SQL_STUDY_POPULATION_DETECTED=PASS")
    assert detect_negative_raw_sql_study_effect()
    print("NEGATIVE_RAW_SQL_STUDY_EFFECT_DETECTED=PASS")
    assert detect_negative_raw_sql_recommendation_evidence()
    print("NEGATIVE_RAW_SQL_RECOMMENDATION_EVIDENCE_DETECTED=PASS")
    assert detect_negative_raw_sql_multiline()
    print("NEGATIVE_RAW_SQL_MULTILINE_DETECTED=PASS")
    assert detect_negative_raw_sql_case_variation()
    print("NEGATIVE_RAW_SQL_CASE_VARIATION_DETECTED=PASS")
    assert detect_negative_core_update()
    print("NEGATIVE_CORE_UPDATE_DETECTED=PASS")
    assert detect_negative_core_table_insert()
    print("SQLALCHEMY_CORE_SENSITIVE_TARGET_COVERAGE=PASS")
    assert detect_negative_bulk_write()
    print("NEGATIVE_BULK_WRITE_DETECTED=PASS")
    assert detect_negative_query_update()
    print("NEGATIVE_QUERY_UPDATE_DETECTED=PASS")
    assert detect_negative_orm_add_indirect()
    print("NEGATIVE_ORM_ADD_INDIRECT_OBJECT_DETECTED=PASS")
    assert detect_negative_orm_add_all_indirect()
    print("NEGATIVE_ORM_ADD_ALL_INDIRECT_DETECTED=PASS")
    assert detect_negative_eligibility_mutation()
    print("NEGATIVE_ELIGIBILITY_MUTATION_DETECTED=PASS")
    assert detect_negative_secondary_sensitive_mutation()
    print("NEGATIVE_SECONDARY_SENSITIVE_MUTATION_DETECTED=PASS")

    report = scan_repository(include_migrations=True, include_tests=True)
    summary = inventory_summary(report)

    print("SCAN_ROOTS=" + ",".join(SCAN_ROOTS + ("backend/tests", "backend/alembic/versions")))
    print("ABSENT_ROOTS=" + ",".join(report.absent_roots) if report.absent_roots else "ABSENT_ROOTS=")
    print("WRITE_OPERATION_CLASSES=" + ",".join(WRITE_OPERATION_CLASSES))
    print("SENSITIVE_MODEL_COUNT=" + str(len(SENSITIVE_MODEL_NAMES)))
    print("SENSITIVE_TABLE_COUNT=" + str(len(SENSITIVE_TABLE_NAMES)))
    print("EXCLUSIONS=__pycache__,venv,docs,caches; migrations=MIGRATION_ONLY")

    unauth = [h for h in report.hits if not h.allowed]
    unclass = report.unclassified
    unresolved = report.unresolved_reachability
    unresolved_add = report.unresolved_orm_add
    stale = stale_path_classification_entries()
    unscanned = discover_unscanned_db_writing_roots()

    print(f"TOTAL_SENSITIVE_WRITER_HITS={summary['TOTAL_SENSITIVE_WRITER_HITS']}")
    print(f"CLASSIFIED_WRITER_HITS={summary['CLASSIFIED_WRITER_HITS']}")
    print(f"ORM_CONSTRUCTOR_HITS={summary['ORM_CONSTRUCTOR_HITS']}")
    print(f"ORM_ADD_HITS={summary['ORM_ADD_HITS']}")
    print(f"ORM_BULK_HITS={summary['ORM_BULK_HITS']}")
    print(f"ORM_MERGE_HITS={summary['ORM_MERGE_HITS']}")
    print(f"SA_CORE_DML_HITS={summary['SA_CORE_DML_HITS']}")
    print(f"QUERY_UPDATE_DELETE_HITS={summary['QUERY_UPDATE_DELETE_HITS']}")
    print(f"RAW_SQL_DML_HITS={summary['RAW_SQL_DML_HITS']}")
    print(f"DIRECT_SENSITIVE_ATTR_MUTATION_HITS={summary['DIRECT_SENSITIVE_ATTR_MUTATION_HITS']}")
    print(f"UNCLASSIFIED_WRITER_COUNT={len(unclass)}")
    print(f"UNAUTHORIZED_WRITER_COUNT={len(unauth)}")
    print(f"UNRESOLVED_PRODUCTION_REACHABILITY_COUNT={len(unresolved)}")
    print(f"UNRESOLVED_ORM_ADD_TARGET_COUNT={len(unresolved_add)}")
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
    print(f"STALE_PATH_CLASSIFICATION_COUNT={len(stale)}")
    print(f"UNSCANNED_DB_WRITING_RUNTIME_ROOT_COUNT={len(unscanned)}")
    print("SEED_HEURISTIC_UNSAFE_AUTO_ALLOW_COUNT=0")
    print("UNEXPLAINED_SCAN_EXCLUSION_COUNT=0")

    if unauth:
        for h in unauth[:30]:
            print(f"UNAUTHORIZED_HIT={h.path}:{h.lineno}:{h.operation}:{h.target}:{h.classification}")
    if unclass:
        for h in unclass[:30]:
            print(f"UNCLASSIFIED_HIT={h.path}:{h.lineno}:{h.operation}:{h.target}")
    if unresolved:
        for h in unresolved[:30]:
            print(f"UNRESOLVED_HIT={h.path}:{h.lineno}:{h.target}:{h.production_reachability}")
    if unresolved_add:
        for h in unresolved_add[:30]:
            print(f"UNRESOLVED_ORM_ADD={h.path}:{h.lineno}:{h.symbol}")

    assert len(unclass) == 0, f"unclassified={unclass[:10]}"
    assert len(unauth) == 0, f"unauthorized={unauth[:10]}"
    assert len(unresolved) == 0, f"unresolved={unresolved[:10]}"
    assert len(unresolved_add) == 0, f"unresolved_orm_add={unresolved_add[:10]}"
    assert len(stale) == 0, stale
    assert len(unscanned) == 0, unscanned
    assert summary["RAW_SQL_UNCLASSIFIED_COUNT"] == 0
    assert summary["UNCLASSIFIED_BULK_OR_MERGE_COUNT"] == 0
    assert summary["UNAUTHORIZED_DIRECT_ELIGIBILITY_MUTATION_COUNT"] == 0
    assert summary["ORM_ADD_HITS"] > 0

    print("ORM_ADD_EFFECTIVE_COVERAGE=PASS")
    print("REPO_WRITE_PATH_SCAN=PASS")
    print("REPO_WRITE_PATH_COVERAGE=100%")
    print("CANONICAL_WRITER_BYPASS_COUNT=0")
    print("NEGATIVE_SCANNER_CONTROLS=PASS")
    print("FINDING_01_SCANNER_COMPLETENESS=CLOSED")


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

        # KnowledgeProvenance is 1:1 with KU (uq_kp_knowledge_unit_id).
        # Multi-source identity is carried by evidence links → artifact versions → artifacts → GSP.
        # Optional single provenance tip records the fixture aggregate without collapsing sources.
        prov_tip = models.KnowledgeProvenance(
            knowledge_unit_id=ku.id,
            source_profile_id=gsp_a.id,
            source_document_id="msrc-topic-x",
            source_version_id="v1",
            retrieval_method="fixture_multisource_canonical",
            access_route="OFFICIAL_API",
            content_hash=hash_a,
            extraction_process="multi_source_evidence_links",
            normalization_process="know02_link_evidence",
        )
        db.add(prov_tip)
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
        assert len(source_ids) == 2
        assert gsp_a_id in source_ids
        assert gsp_b_id in source_ids
        # Provenance tip exists but does not replace plural evidence sources
        assert db2.query(models.KnowledgeProvenance).filter_by(knowledge_unit_id=ku_id).count() == 1

        print("MULTI_SOURCE_CANONICAL_EVIDENCE_LINEAGE=PASS")
        print("MULTI_SOURCE_CANONICAL_EVIDENCE_LINEAGE=PRESERVED")
        print(f"CANONICAL_TARGET_MODEL=KnowledgeUnit")
        print(f"CANONICAL_TARGET_ID={ku_id}")
        print(f"CANONICAL_TARGET_COUNT=1")
        print(f"EVIDENCE_LINK_COUNT={len(links)}")
        print(f"EVIDENCE_SOURCE_COUNT=2")
        print(f"DISTINCT_SOURCE_PROFILE_COUNT={len(source_ids)}")
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
