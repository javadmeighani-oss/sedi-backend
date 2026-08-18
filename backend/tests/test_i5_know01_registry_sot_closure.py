"""I5 Closure-01 — Registry SoT / authority assessment / durable format gap / catalog coverage."""

from __future__ import annotations

import ast
import os
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.i5.adapters.base import AdapterFrameworkError
from backend.app.services.i5.enums import (
    SourceAuthorityClass,
    SourceRole,
)
from backend.app.services.i5.know01.authority_assessment import (
    assess_authority_for_source_profile,
    assess_authority_from_registry_evidence,
    persist_discovery_candidate,
)
from backend.app.services.i5.know01.format_capability_matrix import select_adapter_mode
from backend.app.services.i5.know01.format_gap_persistence import (
    FORMAT_GAP_PERSISTENCE_AUTHORITY,
    format_gap_persistence_authority,
    persist_unsupported_format_gap,
    requery_unsupported_format_gap,
)
from backend.app.services.i5.know01.reference_coverage_matrix import (
    COVERED,
    METADATA_VERIFIED,
    assure_reference_metadata,
    build_reference_catalog_coverage_matrix,
    coverage_manifest_authority,
    matrix_summary,
)
from backend.app.services.i5.know05.coverage_engine import CoveragePrioritizationItem
from backend.app.services.i5.know05.source_selection import (
    HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT,
    NO_ELIGIBLE_GOVERNED_SOURCE,
    assert_no_hardcoded_source_key_eligibility_fallbacks,
    select_connectors_for_gap,
)


def _db_url():
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _require_065(engine) -> None:
    with engine.connect() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "067_i7_lifelong_memory_foundation", head


def _guideline_item(gap_key: str = "guideline-gap") -> CoveragePrioritizationItem:
    return CoveragePrioritizationItem(
        cell_id=1,
        concept_id=1,
        dimension_code="PREVENTION",
        evidence_class="GUIDELINE",
        cell_state="MISSING",
        priority="P0",
        p0_overlay=True,
        gap_key=gap_key,
    )


def test_static_no_hardcoded_source_key_routes_and_no_or_true_tautology():
    assert HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT == 0
    assert_no_hardcoded_source_key_eligibility_fallbacks()
    sel_path = Path("backend/app/services/i5/know05/source_selection.py")
    text_src = sel_path.read_text(encoding="utf-8")
    assert "fallback_missing_literature" not in text_src
    assert "_EVIDENCE_CLASS_ROUTES:" not in text_src
    assert "_DIMENSION_HINTS:" not in text_src
    orch = Path("backend/app/services/i5/know05/orchestrator.py").read_text(encoding="utf-8")
    assert "chosen_keys = list(plan.connectors" not in orch
    # Guard newly touched tests: no `assert <expr> or True` escapes
    touched = [
        Path("backend/tests/test_i5_know01_foundation_gate.py"),
        Path("backend/tests/test_i5_know01_registry_sot_closure.py"),
    ]
    for p in touched:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert) and isinstance(node.test, ast.BoolOp):
                if isinstance(node.test.op, ast.Or):
                    for v in node.test.values:
                        if isinstance(v, ast.Constant) and v.value is True:
                            raise AssertionError(f"TAUTOLOGICAL_OR_TRUE:{p}")

def test_f2_authority_assessment_evidence_derived_unit():
    fake = assess_authority_from_registry_evidence(
        candidate_identity="best-medical-guidelines.health",
        authority_class=SourceAuthorityClass.UNVERIFIED.value,
        hostname_hint="best-medical-guidelines.health",
    )
    assert fake.authority_verified is False
    assert fake.auto_trust is False
    assert fake.auto_activate is False
    assert fake.eligible_for_activation is False
    assert "MEDICAL_LOOKING_HOSTNAME_INSUFFICIENT" in fake.blocking_reasons or fake.assessment_status == (
        "AUTHORITY_REVIEW_REQUIRED"
    )

    identity_only = assess_authority_from_registry_evidence(
        candidate_identity="know01:offseed_academic_lookalike",
        authority_class=SourceAuthorityClass.UNVERIFIED.value,
        publisher_family="Some University Press Lookalike",
        canonical_home="https://papers.example.edu",
    )
    assert identity_only.authority_verified is False
    assert identity_only.requires_human_governance_review is True
    assert identity_only.eligible_for_activation is False

    insufficient = assess_authority_from_registry_evidence(
        candidate_identity="know01:who_int",
        authority_class=SourceAuthorityClass.GLOBAL_INTERGOVERNMENTAL.value,
        publisher_family="WHO",
        # missing last_authority_verification + roles
        canonical_home="https://www.who.int",
    )
    assert insufficient.authority_verified is False
    assert insufficient.assessment_status == "AUTHORITY_REVIEW_REQUIRED"
    assert "INSUFFICIENT_AUTHORITY_EVIDENCE" in insufficient.blocking_reasons

    strong = assess_authority_from_registry_evidence(
        candidate_identity="know01:who_int",
        authority_class=SourceAuthorityClass.GLOBAL_INTERGOVERNMENTAL.value,
        publisher_family="WHO",
        canonical_home="https://www.who.int",
        last_authority_verification=datetime.utcnow(),
        roles=(SourceRole.CLINICAL_GUIDELINE.value, SourceRole.PUBLIC_HEALTH.value),
        source_universe="GLOBAL_KNOWLEDGE",
        api_endpoint="https://www.who.int/api",
    )
    assert strong.authority_verified is True
    assert strong.assessment_status == "AUTHORITY_EVIDENCE_SUFFICIENT"
    assert strong.eligible_to_proceed_to_rights_review is True
    assert strong.eligible_for_activation is False
    assert strong.auto_trust is False
    assert strong.auto_activate is False
    assert "last_authority_verification" in strong.evidence_used


def test_f3_format_gap_authority_and_unit_routing():
    meta = format_gap_persistence_authority()
    assert meta["FORMAT_GAP_PERSISTENCE_AUTHORITY"] == FORMAT_GAP_PERSISTENCE_AUTHORITY
    assert "KnowledgeGap" in FORMAT_GAP_PERSISTENCE_AUTHORITY
    with pytest.raises(AdapterFrameworkError, match="UNSUPPORTED_FORMAT"):
        select_adapter_mode(filename_hint="chapter.epub")


def test_f4_manifest_coverage_matrix_complete():
    auth = coverage_manifest_authority()
    assert auth["entity_count"] == 19
    assert Path(auth["path"]).name == "coverage_manifest_v1.yaml"
    cells = build_reference_catalog_coverage_matrix()
    summary = matrix_summary(cells)
    assert summary["entity_count"] == 19
    assert summary["unmapped_manifest_entity_count"] == 0
    assert summary["placeholder_as_completeness_evidence_count"] == 0
    # Every entity has explicit classification
    assert all(c.coverage_status for c in cells)
    # ALS/MS should have disease-tagged authority coverage
    als = next(c for c in cells if c.entity_id == "D18")
    ms = next(c for c in cells if c.entity_id == "D19")
    assert als.authority_coverage in {COVERED, "PARTIAL"}
    assert ms.authority_coverage in {COVERED, "PARTIAL"}
    assert "ALS" in " ".join(als.named_references).upper() or any(
        "als" in r or "genereviews" in r or "braddom" in r or "harrison" in r for r in als.named_references
    )
    # Harrison must not alone mark specialty-only entities COVERED via broad IM
    ophtho = next(c for c in cells if c.entity_id == "D07")
    if ophtho.named_references == ["harrisons_principles_internal_medicine"]:
        assert ophtho.authority_coverage != COVERED
    meta = assure_reference_metadata()
    assert meta
    assert all(m.status in {METADATA_VERIFIED, "METADATA_PARTIALLY_VERIFIED", "METADATA_REVIEW_REQUIRED"} for m in meta)
    # Rights independent of authority: commercial/metadata books remain non-fulltext
    assert any(c.automated_fulltext_acquisition != "OPEN_OR_AUTOMATABLE_REFERENCE_AVAILABLE" for c in cells)


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_pg_f1_registry_source_of_truth_fixtures():
    from backend.app import models
    from backend.tests._know05_test_fixtures import seed_governed_role_source

    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        # Fixture A — two eligible guideline sources (no source-key route required)
        seed_governed_role_source(
            db,
            connector_key="synth_guideline_alpha",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            publisher_family="Alpha Guideline Body",
            canonical_home="https://alpha-guidelines.example.org",
            api_endpoint="https://alpha-guidelines.example.org/api",
        )
        seed_governed_role_source(
            db,
            connector_key="synth_guideline_beta",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            publisher_family="Beta Guideline Body",
            canonical_home="https://beta-guidelines.example.org",
            api_endpoint="https://beta-guidelines.example.org/api",
        )
        # Fixture B — brand-new key not in any historical source-selection constant
        seed_governed_role_source(
            db,
            connector_key="synth_registry_only_gamma_2026",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            publisher_family="Gamma Registry Body",
            canonical_home="https://gamma-guidelines.example.org",
            api_endpoint="https://gamma-guidelines.example.org/v1",
        )
        # Fixture C — blocked rights
        seed_governed_role_source(
            db,
            connector_key="synth_guideline_blocked",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            rights_mode="DENIED",
            publisher_family="Blocked Body",
            canonical_home="https://blocked-guidelines.example.org",
            api_endpoint="https://blocked-guidelines.example.org/api",
        )
        db.commit()

        sels = select_connectors_for_gap(db, _guideline_item())
        crawl = [s for s in sels if s.selected_for_crawl]
        keys = {s.connector_key for s in crawl}
        assert "synth_guideline_alpha" in keys
        assert "synth_guideline_beta" in keys
        assert "synth_registry_only_gamma_2026" in keys
        assert "synth_guideline_blocked" not in keys
        blocked = [s for s in sels if s.connector_key == "synth_guideline_blocked"]
        assert blocked
        assert blocked[0].selected_for_crawl is False
        assert blocked[0].automation_decision == "BLOCKED"

        # Negative: handler-known key without Registry eligibility must not crawl
        # (clinicaltrials adapter exists in code; without ACTIVE+ALLOWED registry → not selected)
        bare_item = CoveragePrioritizationItem(
            cell_id=2,
            concept_id=2,
            dimension_code="CLINICAL_TRIALS",
            evidence_class="CLINICAL_TRIALS",
            cell_state="MISSING",
            priority="P0",
            p0_overlay=True,
            gap_key="trials-no-registry",
        )
        # Ensure CT.gov is not accidentally ACTIVE+ALLOWED from other suite fixtures:
        ct = (
            db.query(models.GovernedSourceProfile)
            .filter_by(canonical_key="know01:clinicaltrials_gov_api_v2")
            .first()
        )
        if ct is not None:
            ct.registry_state = "DISCOVERED"
            ct.runtime_eligibility = "NOT_ELIGIBLE"
            ext = (
                db.query(models.I5SourceRegistryExtension)
                .filter_by(source_profile_id=ct.id)
                .first()
            )
            if ext is not None:
                ext.automation_right = "UNKNOWN"
                ext.access_right = "UNKNOWN"
                ext.registry_status = "DISCOVERED"
            db.commit()

        trial_sels = select_connectors_for_gap(db, bare_item)
        trial_crawl = [s for s in trial_sels if s.selected_for_crawl]
        assert not any(s.connector_key == "clinicaltrials_gov_api_v2" for s in trial_crawl)

        # Fixture D — terminology role only (no DIAGNOSIS dimension side-roles)
        term_item = CoveragePrioritizationItem(
            cell_id=3,
            concept_id=3,
            dimension_code="TERMINOLOGY_ONLY",
            evidence_class="TERMINOLOGY",
            cell_state="MISSING",
            priority="P2",
            p0_overlay=False,
            gap_key="term-gap",
        )
        for role_row in db.query(models.I5SourceRegistryRole).filter_by(
            role=SourceRole.BIOMEDICAL_TERMINOLOGY.value
        ).all():
            g = db.query(models.GovernedSourceProfile).filter_by(id=role_row.source_profile_id).first()
            if g:
                g.registry_state = "DISCOVERED"
                g.runtime_eligibility = "NOT_ELIGIBLE"
            ext = (
                db.query(models.I5SourceRegistryExtension)
                .filter_by(source_profile_id=role_row.source_profile_id)
                .first()
            )
            if ext is not None:
                ext.automation_right = "UNKNOWN"
                ext.access_right = "UNKNOWN"
        db.commit()
        term_sels = select_connectors_for_gap(db, term_item)
        assert any(s.connector_key == NO_ELIGIBLE_GOVERNED_SOURCE for s in term_sels)
        assert not any(s.selected_for_crawl for s in term_sels)
        print(
            f"F1_CRAWL_KEYS={sorted(keys)} "
            f"BLOCKED_SELECTED_FOR_CRAWL=NO "
            f"NO_ELIGIBLE_FAIL_CLOSED=PASS"
        )
    finally:
        db.close()
        engine.dispose()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_pg_f2_authority_persist_discovery_and_institutional():
    from backend.tests._know05_test_fixtures import seed_governed_role_source

    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        gsp = seed_governed_role_source(
            db,
            connector_key="who_authority_proof",
            roles=(SourceRole.CLINICAL_GUIDELINE.value,),
            authority_class=SourceAuthorityClass.GLOBAL_INTERGOVERNMENTAL.value,
            publisher_family="WHO",
            canonical_home="https://www.who.int",
            api_endpoint="https://www.who.int/api",
            mark_authority_verified=True,
        )
        db.commit()
        assessed = assess_authority_for_source_profile(db, gsp.id)
        assert assessed.authority_verified is True
        assert assessed.auto_trust is False
        assert assessed.eligible_for_activation is False
        assert "authority_class=GLOBAL_INTERGOVERNMENTAL" in assessed.evidence_used

        # Persist discovery candidate → new session requery non-active
        fake = assess_authority_from_registry_evidence(
            candidate_identity="know01:discovered_offseed_candidate",
            authority_class=SourceAuthorityClass.UNVERIFIED.value,
            hostname_hint="best-medical-guidelines.health",
        )
        cand = persist_discovery_candidate(
            db,
            candidate_key="discovered_offseed_candidate",
            locator="https://best-medical-guidelines.health/x",
            seed_org_domain="best-medical-guidelines.health",
            assessment=fake,
            roles=(),
        )
        db.commit()
        cand_id = cand.id
        db.close()

        db2 = Session()
        from backend.app import models

        again = db2.query(models.GovernedSourceProfile).filter_by(id=cand_id).one()
        assert again.registry_state == "DISCOVERED"
        assert again.runtime_eligibility == "NOT_ELIGIBLE"
        ext = (
            db2.query(models.I5SourceRegistryExtension)
            .filter_by(source_profile_id=cand_id)
            .one()
        )
        assert (ext.registry_status or "").upper() == "DISCOVERED"
        assert "AUTONOMOUS_TRUST=NO" in (ext.notes or "")
        reassess = assess_authority_for_source_profile(db2, cand_id)
        assert reassess.authority_verified is False
        assert reassess.auto_activate is False
        print(
            f"F2_AUTHORITY_VERIFIED_INSTITUTIONAL=YES "
            f"F2_DISCOVERY_PERSISTED_ID={cand_id} "
            f"F2_AUTO_TRUST=NO"
        )
        db2.close()
    finally:
        try:
            db.close()
        except Exception:
            pass
        engine.dispose()


@pytest.mark.skipif(not _db_url(), reason="TEST_DATABASE_URL not set")
def test_pg_f3_durable_unsupported_format_gap_requery():
    from backend.app import models
    from backend.tests._know05_test_fixtures import seed_governed_role_source

    engine = create_engine(_db_url())
    _require_065(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        gsp = seed_governed_role_source(
            db,
            connector_key="format_gap_source",
            roles=(SourceRole.MEDICAL_REFERENCE_BOOK.value,),
            authority_class=SourceAuthorityClass.REFERENCE_BOOK_PUBLISHER.value,
            publisher_family="Format Gap Press",
        )
        gsp_id = gsp.id
        db.commit()

        false_success = 0
        try:
            select_adapter_mode(filename_hint="monograph.epub")
            false_success += 1
        except AdapterFrameworkError as exc:
            assert "UNSUPPORTED_FORMAT" in str(exc)
            gap, created = persist_unsupported_format_gap(
                db,
                source_profile_id=gsp_id,
                resource_ref="https://example.org/monograph.epub",
                format_id="EPUB",
            )
            assert created is True
            gap_id = gap.id
            key = gap.canonical_gap_key
            db.commit()
        assert false_success == 0

        db.close()
        db2 = Session()
        again = requery_unsupported_format_gap(
            db2,
            source_profile_id=gsp_id,
            resource_ref="https://example.org/monograph.epub",
            format_id="EPUB",
        )
        assert again is not None
        assert again.id == gap_id
        assert again.canonical_gap_key == key
        assert again.target_source_profile_id == gsp_id
        assert (again.blocker or "").startswith("UNSUPPORTED_FORMAT")
        assert again.gap_type == "RUNTIME_RETRIEVAL_FAILURE"

        # Dedupe / version on repeat
        gap2, created2 = persist_unsupported_format_gap(
            db2,
            source_profile_id=gsp_id,
            resource_ref="https://example.org/monograph.epub",
            format_id="EPUB",
        )
        db2.commit()
        assert created2 is False
        assert gap2.id == gap_id
        assert int(gap2.retry_count) >= 1
        assert again.status == "OPEN"
        print(
            f"UNSUPPORTED_FORMAT_FAIL_CLOSED=PASS "
            f"UNSUPPORTED_FORMAT_DURABLE_GAP_CREATED=PASS "
            f"UNSUPPORTED_FORMAT_GAP_REQUERY=PASS "
            f"UNSUPPORTED_FORMAT_FALSE_SUCCESS_COUNT=0 "
            f"GAP_ID={gap_id}"
        )
        db2.close()
    finally:
        try:
            db.close()
        except Exception:
            pass
        engine.dispose()
