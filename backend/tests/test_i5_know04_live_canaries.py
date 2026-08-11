"""I5-KNOW-04 NF15 — mandatory bounded live connector canaries (read-only, no Production writes)."""

from __future__ import annotations

import os

import pytest

from backend.app.services.i5.know04.live_canaries import (
    run_all_mandatory_live_canaries,
    run_ctgov_live_canary,
    run_pmc_live_canary,
    run_pubmed_live_canary,
    run_who_guideline_authority_live_canary,
)


_ALLOWED_STATUSES = frozenset(
    {
        "LIVE_VERIFIED",
        "NOT_EXECUTED_MISSING_CREDENTIALS",
        "NOT_EXECUTED_RIGHTS_BLOCK",
        "NOT_EXECUTED_NETWORK_POLICY",
        "FAILED",
        "NOT_EXECUTED",
    }
)


def _assert_bounded_evidence(ev) -> None:
    assert ev.status in _ALLOWED_STATUSES
    assert ev.status != "PASS"
    assert ev.production_persistence is False
    assert ev.storage_decision == "NO_STORE"
    assert ev.transient_residue == 0
    assert ev.record_count <= 3


def test_pubmed_live_canary_bounded():
    if not os.environ.get("SEDI_NCBI_TOOL") or not os.environ.get("SEDI_NCBI_EMAIL"):
        pytest.skip("SEDI_NCBI_TOOL/SEDI_NCBI_EMAIL required for PubMed live canary")
    ev = run_pubmed_live_canary(max_records=2)
    _assert_bounded_evidence(ev)
    assert ev.network_executed is True
    assert ev.status == "LIVE_VERIFIED"
    assert ev.record_count >= 1
    assert ev.official_host == "eutils.ncbi.nlm.nih.gov"


def test_pmc_live_canary_bounded():
    ev = run_pmc_live_canary(max_records=1)
    _assert_bounded_evidence(ev)
    assert ev.network_executed is True
    assert ev.status == "LIVE_VERIFIED"
    assert ev.record_count >= 1
    assert ev.official_host == "www.ncbi.nlm.nih.gov"


def test_ctgov_live_canary_bounded():
    ev = run_ctgov_live_canary()
    _assert_bounded_evidence(ev)
    assert ev.network_executed is True
    assert ev.status == "LIVE_VERIFIED"
    assert ev.record_count >= 1
    assert ev.official_host == "clinicaltrials.gov"


def test_who_guideline_authority_live_canary_nf14():
    ev = run_who_guideline_authority_live_canary()
    _assert_bounded_evidence(ev)
    assert ev.network_executed is True
    assert ev.status == "LIVE_VERIFIED"
    assert ev.record_count >= 1
    assert "news_as_guideline=0" in ev.parser_result
    assert "recommendation_extraction=NOT_EXERCISED" in ev.parser_result


def test_mandatory_live_canaries_suite():
    """NF15 — all four bounded official connectors must live-verify in CI job 2."""
    if not os.environ.get("SEDI_NCBI_TOOL") or not os.environ.get("SEDI_NCBI_EMAIL"):
        pytest.skip("SEDI_NCBI_TOOL/SEDI_NCBI_EMAIL required for full mandatory suite")
    results = run_all_mandatory_live_canaries()
    assert set(results.keys()) == {"pubmed", "pmc", "ctgov", "who_guideline_authority"}
    for name, ev in results.items():
        _assert_bounded_evidence(ev)
        assert ev.status == "LIVE_VERIFIED", f"{name} status={ev.status} parser={ev.parser_result}"
