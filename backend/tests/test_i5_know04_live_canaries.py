"""I5-KNOW-04/05 live canaries — NF15 + NF16/NF17 observability."""

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
from backend.app.services.i5.know05.ncbi_identity import is_disallowed_operational_email


_ALLOWED_STATUSES = frozenset(
    {
        "LIVE_VERIFIED",
        "NOT_EXECUTED_MISSING_CREDENTIALS",
        "NOT_EXECUTED_RIGHTS_BLOCK",
        "NOT_EXECUTED_NETWORK_POLICY",
        "FAILED",
        "NOT_EXECUTED",
        "BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY",
    }
)


def _assert_bounded_evidence(ev) -> None:
    assert ev.status in _ALLOWED_STATUSES
    assert ev.status != "PASS"
    assert ev.production_persistence is False
    assert ev.storage_decision == "NO_STORE"
    assert ev.transient_residue == 0
    assert ev.record_count <= 3
    if ev.status == "LIVE_VERIFIED":
        assert ev.http_status >= 200 and ev.http_status < 300
        assert ev.bytes_received > 0
        assert ev.request_count >= 1


def test_pubmed_live_canary_bounded():
    ev = run_pubmed_live_canary(max_records=2)
    _assert_bounded_evidence(ev)
    assert ev.official_host == "eutils.ncbi.nlm.nih.gov"
    if ev.status == "BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY":
        assert ev.network_executed is False
        return
    assert ev.network_executed is True
    assert ev.status == "LIVE_VERIFIED"
    assert ev.record_count >= 1


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
    """NF15 — PMC/CT.gov/WHO must live-verify; PubMed may honest-block on NF16."""
    results = run_all_mandatory_live_canaries()
    assert set(results.keys()) == {"pubmed", "pmc", "ctgov", "who_guideline_authority"}
    for name, ev in results.items():
        _assert_bounded_evidence(ev)
        if name == "pubmed":
            assert ev.status in {
                "LIVE_VERIFIED",
                "BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY",
            }, f"pubmed status={ev.status}"
            email = os.environ.get("SEDI_NCBI_EMAIL", "")
            if email and is_disallowed_operational_email(email):
                assert ev.status == "BLOCKED_MISSING_VALID_OPERATIONAL_IDENTITY"
        else:
            assert ev.status == "LIVE_VERIFIED", f"{name} status={ev.status} parser={ev.parser_result}"
