"""I5-KNOW-05 live bounded ingestion — CT.gov positive path (no Production persistence)."""

from __future__ import annotations

from backend.app.services.i5.know05.bounded_ingestion import (
    ingest_clinicaltrials_bounded,
    ingest_pubmed_bounded_or_block,
)
from backend.app.services.i5.know05.modes import Know05Mode


def test_nf19_live_ctgov_bounded_beyond_ready_for_fetch():
    """Real network CT.gov bounded path; PubMed remains exact-blocked without NCBI identity."""
    pubmed = ingest_pubmed_bounded_or_block(mode=Know05Mode.BOUNDED_INGESTION)
    assert pubmed.status == "BLOCKED"
    assert pubmed.block_reason
    assert "READY_FOR_BOUNDED_FETCH" not in pubmed.status

    result = ingest_clinicaltrials_bounded(
        None,
        mode=Know05Mode.BOUNDED_INGESTION,
        query="diabetes type 2",
        max_records=1,
        persist=False,
    )
    # Exact fail-closed on network/SSL issues (local); CI ubuntu must get FETCHED
    if result.status == "FAILED" and result.block_reason and "NETWORK_OR_CONNECTOR_ERROR" in result.block_reason:
        import pytest

        pytest.fail(f"CTGOV_BOUNDED_NETWORK_FAILED:{result.block_reason}")
    assert result.status == "FETCHED"
    assert result.request_count >= 1
    assert result.http_status and 200 <= result.http_status < 300
    assert result.bytes_received > 0
    assert result.records_discovered >= 1
    assert result.records_accepted >= 1
    assert result.external_ids
    assert result.transient_raw_residue == 0
    assert result.storage_decision == "NO_STORE"
    assert "RUNTIME_ELIGIBILITY" in result.publication_stages
    assert result.status != "READY_FOR_BOUNDED_FETCH"
