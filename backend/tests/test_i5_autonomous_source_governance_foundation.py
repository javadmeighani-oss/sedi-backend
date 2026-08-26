"""Autonomous discovery + qualification + monitoring foundation — offline tests."""
from __future__ import annotations

from backend.app.services.i5.autonomous_source_governance import (
    ACTIVATION_HARD_BLOCK,
    assert_no_auto_activation,
    build_d01_d19_matrix,
    candidate_identity_key,
    discover_candidates,
    merge_discovered_into_registry,
    monitor_active_and_qualified,
    normalize_domain,
    normalize_url_family,
    qualify_candidate,
    run_foundation_pipeline,
    status_counts,
)
from backend.app.services.i5.candidate_qualification_registry import (
    ALLOWED_STATUSES,
    assert_no_auto_activation_except,
    candidate_rows,
    load_candidate_qualification_registry,
)
from backend.app.services.i5.trusted_source_manifest import (
    active_manifest_rows,
    load_trusted_source_manifest,
)


def test_allowed_statuses_include_discovered():
    assert "DISCOVERED" in ALLOWED_STATUSES
    assert ALLOWED_STATUSES == {"DISCOVERED", "QUALIFIED", "REJECTED", "NEEDS_REVIEW"}


def test_discovery_creates_candidates_never_active():
    rows = discover_candidates(include_wave02_gaps=False)
    assert len(rows) >= 4
    for r in rows:
        assert r["qualification_status"] == "DISCOVERED"
        assert str(r["activation"]).upper() == "NO"
        assert r.get("candidate_id")
        assert r.get("canonical_domain")
        assert r.get("candidate_url_family")
        assert r.get("discovery_method")
        assert r.get("discovered_at")


def test_duplicate_candidate_suppression_across_aliases():
    base = candidate_rows()
    discovered = discover_candidates(include_wave02_gaps=False)
    merged, stats = merge_discovered_into_registry(discovered, base_rows=base)
    # Alias seed for cancer.gov PDQ must not inflate a second NCI identity
    nci_like = [
        r
        for r in merged
        if normalize_domain(str(r.get("canonical_domain") or "")) == "cancer.gov"
        and "pdq" in normalize_url_family(str(r.get("candidate_url_family") or r.get("url_family") or ""))
    ]
    assert len(nci_like) == 1
    assert stats["duplicate_suppressed"] >= 1
    assert stats["new_candidates"] >= 1
    # History preserved on existing rows
    for r in merged:
        if r.get("candidate_id") == "nci_pdq_oncology":
            assert r.get("history") is not None
            assert r.get("last_seen")


def test_identity_key_normalizes_www_and_slash():
    a = candidate_identity_key(
        canonical_domain="www.cancer.gov",
        candidate_url_family="https://www.cancer.gov/publications/pdq/",
    )
    b = candidate_identity_key(
        canonical_domain="cancer.gov",
        candidate_url_family="https://cancer.gov/publications/pdq",
    )
    assert a == b


def test_qualification_transitions_never_activate():
    disc = discover_candidates(include_wave02_gaps=False)[0]
    out = qualify_candidate(disc, live=False)
    assert out["qualification_status"] in ALLOWED_STATUSES
    assert out["qualification_status"] != "DISCOVERED" or out.get("qualification_reason")
    assert str(out["activation"]).upper() == "NO"
    assert out.get("history")


def test_owh_cdc_child_ncezid_remain_inactive_hard_block():
    rows = {r["candidate_id"]: r for r in candidate_rows()}
    for cid in ACTIVATION_HARD_BLOCK:
        assert cid in rows
        q = qualify_candidate(rows[cid], live=False)
        assert str(q["activation"]).upper() == "NO"
        assert q["qualification_status"] in {"NEEDS_REVIEW", "QUALIFIED", "REJECTED"}
        # Even if authority looks official, CDC broaden / OWH stay non-activating NEEDS_REVIEW
        if cid.startswith("cdc_") or cid.startswith("owh_"):
            assert q["qualification_status"] == "NEEDS_REVIEW"


def test_pipeline_no_auto_activation_and_matrix():
    report = run_foundation_pipeline(live=False, include_wave02_gaps=False)
    assert report["auto_activation"] == "NO"
    assert report["new_source_activation"] == "NO"
    assert report["new_candidates"] >= 1 or report["duplicate_suppressed"] >= 1
    assert report["candidate_after"] >= report["candidate_before"]
    assert_no_auto_activation(report["candidates"])
    assert report["owh_activation"] == "NO"
    assert report["cdc_child_activation"] == "NO"
    assert report["cdc_ncezid_activation"] == "NO"
    matrix = report["d01_d19_matrix"]
    assert len(matrix) == 19
    assert {r["dxx"] for r in matrix} == {f"D{i:02d}" for i in range(1, 20)}
    for r in matrix:
        assert r["depth_state"] in {"STRONG", "MODERATE", "THIN", "UNCOVERED"}


def test_monitor_offline_emits_findings():
    rows = candidate_rows()
    findings = monitor_active_and_qualified(rows, live=False, max_subjects=5)
    assert len(findings) >= 1
    assert all("change_kind" in f for f in findings)


def test_active_allowlist_still_eleven_and_registry_no_activation():
    load_trusted_source_manifest.cache_clear()
    load_candidate_qualification_registry.cache_clear()
    assert len(active_manifest_rows()) == 11
    assert_no_auto_activation_except(allowed_active_keys=set())
    counts = status_counts(candidate_rows())
    assert counts["NEEDS_REVIEW"] >= 3
    assert counts["QUALIFIED"] >= 9


def test_matrix_builder_standalone():
    matrix = build_d01_d19_matrix(
        per_dxx={
            "D17": {"ku": 6, "eligible": 5, "kce": 10},
            "D18": {"ku": 3, "eligible": 2, "kce": 4},
            "D19": {"ku": 4, "eligible": 2, "kce": 4},
        },
        serving_proof={"D17": "PASS", "D18": "PASS", "D19": "PASS"},
    )
    d17 = next(r for r in matrix if r["dxx"] == "D17")
    assert d17["serving_proof"] == "PASS"
    assert d17["depth_state"] in {"STRONG", "MODERATE"}
