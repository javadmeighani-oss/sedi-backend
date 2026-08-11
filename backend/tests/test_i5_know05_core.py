"""I5-KNOW-05 deterministic tests — modes, NF16/NF17, coverage gaps, RAG coherence, matrices."""

from __future__ import annotations

import os

import pytest

from backend.app.services.i5.know04.live_canaries import ObservingHttpGet, LiveCanaryEvidence
from backend.app.services.i5.know05.availability import (
    assert_runtime_eligible_has_retrieval,
    derive_ku_availability,
)
from backend.app.services.i5.know05.budgets import assert_within_budget, plan_bounded_ingestion
from backend.app.services.i5.know05.modes import Know05Mode, Know05ModeError, assert_mode_authorized
from backend.app.services.i5.know05.ncbi_identity import (
    is_disallowed_operational_email,
    load_ncbi_operational_identity,
)
from backend.app.services.i5.know05.publication import (
    PublicationCandidate,
    PublicationPipelineError,
    PublicationStage,
    advance_stage,
    assert_no_direct_runtime_publish,
)
from backend.app.services.i5.know05.source_discovery import (
    CandidateSource,
    CandidateSourceError,
    CandidateSourceStage,
    advance_candidate,
    assert_discovered_not_authority,
)
from backend.app.services.i5.know05.storage_matrix import matrices_summary


def test_nf16_rejects_test_operational_email():
    assert is_disallowed_operational_email("know04-ci@sedi.test") is True
    assert is_disallowed_operational_email("user@example.com") is True
    assert is_disallowed_operational_email("ops@sedi.health") is False


def test_nf16_weekly_blocked_without_valid_identity(monkeypatch):
    monkeypatch.setenv("SEDI_NCBI_TOOL", "sedi-know05")
    monkeypatch.setenv("SEDI_NCBI_EMAIL", "know04-ci@sedi.test")
    ident = load_ncbi_operational_identity(require_for_weekly=True)
    assert ident.weekly_operation_status == "BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY"


def test_nf16_weekly_ready_with_valid_identity(monkeypatch):
    monkeypatch.setenv("SEDI_NCBI_TOOL", "sedi-know05")
    monkeypatch.setenv("SEDI_NCBI_EMAIL", "ncbi-ops@rimiyadesign.com")
    ident = load_ncbi_operational_identity(require_for_weekly=True)
    assert ident.weekly_operation_status == "LIVE_READY"
    assert "email" not in ident.as_dict() or ident.as_dict().get("email_redacted") is True


def test_modes_production_weekly_forbidden():
    with pytest.raises(Know05ModeError):
        assert_mode_authorized(Know05Mode.PRODUCTION_WEEKLY)
    assert_mode_authorized(Know05Mode.DRY_RUN)
    assert_mode_authorized(Know05Mode.BOUNDED_INGESTION)


def test_budgets_bounded_no_unbounded():
    plan = plan_bounded_ingestion(Know05Mode.BOUNDED_INGESTION)
    assert plan.as_dict()["unbounded_crawl"] is False
    assert plan.budget.max_records <= 100
    assert_within_budget(records=10, requests=5, pages=1, budget=plan.budget)
    with pytest.raises(ValueError, match="RECORD_BUDGET"):
        assert_within_budget(records=9999, requests=1, pages=1, budget=plan.budget)


def test_publication_pipeline_no_source_to_runtime():
    with pytest.raises(PublicationPipelineError):
        assert_no_direct_runtime_publish(
            from_stage=PublicationStage.RAW_SOURCE_RECORD,
            to_stage=PublicationStage.RUNTIME_ELIGIBILITY,
        )
    c = PublicationCandidate(external_identifier="x", source_connector_key="pubmed_ncbi_eutils")
    c = advance_stage(c, PublicationStage.NORMALIZED_CANDIDATE)
    assert c.stage == PublicationStage.NORMALIZED_CANDIDATE
    with pytest.raises(PublicationPipelineError):
        advance_stage(c, PublicationStage.RUNTIME_ELIGIBILITY)


def test_candidate_source_not_authority():
    c = CandidateSource(locator="https://example.org/page")
    assert_discovered_not_authority(c)
    c.clinical_authority = True
    with pytest.raises(CandidateSourceError):
        assert_discovered_not_authority(c)
    c.clinical_authority = False
    c = advance_candidate(c, CandidateSourceStage.AUTHORITY_VERIFIED)
    assert c.stage == CandidateSourceStage.AUTHORITY_VERIFIED


def test_availability_runtime_requires_retrieval():
    view = derive_ku_availability(
        ku_id=1,
        runtime_eligibility="ELIGIBLE",
        retraction_reason=None,
        freshness_state="CURRENT",
        provenance_complete=True,
        has_structured_links=True,
        rag_indexed=False,
    )
    assert view.runtime_eligible is True
    assert "STRUCTURED_SQL" in view.retrieval_strategies
    assert_runtime_eligible_has_retrieval(view)
    retracted = derive_ku_availability(
        ku_id=2,
        runtime_eligibility="ELIGIBLE",
        retraction_reason="RETRACTED",
        freshness_state="CURRENT",
        provenance_complete=True,
    )
    assert retracted.runtime_eligible is False
    assert retracted.rag_eligible is False


def test_storage_matrix_no_duplicate_authority():
    s = matrices_summary()
    assert s["duplicate_knowledge_authority"] == 0
    assert s["new_migration"] == "NO"
    assert s["authority_rows"] >= 10
    assert s["storage_rows"] >= 5


def test_nf17_observing_http_get_records_real_bytes():
    class _Resp:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        content = b'{"ok":true}'

    obs = ObservingHttpGet(lambda url, headers=None, timeout=None: _Resp())
    obs("https://example.test/x")
    assert obs.last_status == 200
    assert obs.total_bytes == len(b'{"ok":true}')
    assert obs.request_count == 1
    # Evidence must not hardcode success without observation
    ev = LiveCanaryEvidence(
        connector="t",
        official_host="h",
        request_purpose="p",
        timestamp_utc="Z",
        http_status=obs.last_status,
        content_type=obs.last_content_type,
        record_count=1,
        external_ids=("1",),
        bytes_received=obs.total_bytes,
        rights_decision="METADATA_ONLY",
        storage_decision="NO_STORE",
        transient_residue=0,
        parser_result="PASS",
        network_executed=True,
        production_persistence=False,
        status="LIVE_VERIFIED",
        request_count=obs.request_count,
    )
    assert ev.http_status == 200
    assert ev.bytes_received > 0
