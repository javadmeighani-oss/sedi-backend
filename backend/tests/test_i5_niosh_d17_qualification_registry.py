"""NIOSH D17 qualification + candidate registry — offline tests."""
from __future__ import annotations

import re
from pathlib import Path

from backend.app.services.i5.candidate_qualification_registry import (
    assert_no_auto_activation_except,
    candidate_rows,
    load_candidate_qualification_registry,
    qualification_counts,
)
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    NIOSH_SOURCE_KEY,
    can_apply_specialized_entity_eligibility,
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
    specialized_source_authorized,
)
from backend.app.services.i5.trusted_source_manifest import (
    active_manifest_rows,
    governed_low_risk_eligible,
    load_trusted_source_manifest,
)


def test_candidate_registry_statuses_and_no_auto_activation():
    data = load_candidate_qualification_registry()
    assert data["activation_policy"] == "QUALIFIED_DOES_NOT_AUTO_ACTIVATE"
    counts = qualification_counts()
    assert counts["QUALIFIED"] >= 9
    assert counts["NEEDS_REVIEW"] >= 2
    assert counts["REJECTED"] == 0
    assert_no_auto_activation_except(allowed_active_keys=set())
    for row in candidate_rows():
        assert str(row["activation"]).upper() in {"NO", "FALSE"}
        assert row["qualification_status"] in {"QUALIFIED", "REJECTED", "NEEDS_REVIEW"}


def test_niosh_allowlist_activation_boundary():
    data = load_trusted_source_manifest()
    assert str(data["allowlist_version"]).startswith("i5-multisource-v1")
    rows = active_manifest_rows()
    assert len(rows) >= 5
    by_key = {r["source_key"]: r for r in rows}
    assert NIOSH_SOURCE_KEY in by_key
    niosh = by_key[NIOSH_SOURCE_KEY]
    assert governed_low_risk_eligible(NIOSH_SOURCE_KEY) is False
    assert niosh["rights_terms_state"] == "PUBLIC_DOMAIN"
    assert niosh["robots_access_state"] == "ALLOWED"
    assert "D17" in (niosh.get("specialized_serving_eligibility") or [])
    patterns = [re.compile(p) for p in (niosh.get("allowed_url_patterns") or [])]
    urls = [niosh["exact_url"]] + list(niosh.get("additional_urls") or [])
    for url in urls:
        assert any(p.match(url) for p in patterns), url
        assert "/niosh/archive/" not in url
    assert not any(p.match("https://www.cdc.gov/niosh/archive/foo") for p in patterns)
    cdc = by_key["cdc_health_lifestyle"]
    cdc_patterns = " ".join(cdc.get("allowed_url_patterns") or [])
    assert "/niosh/" not in cdc_patterns


def test_niosh_specialized_d17_not_other_entities():
    assert specialized_source_authorized(NIOSH_SOURCE_KEY) is True
    assert specialized_allowed_entities_for_source(NIOSH_SOURCE_KEY) == {"D17"}
    assert resolve_specialized_entity_from_url("https://www.cdc.gov/niosh/topics/noise/").entity_id == "D17"
    from types import SimpleNamespace
    from backend.app.services.i5.enums import ConflictState, MedicalSafetyState

    ku = SimpleNamespace(
        provenance_complete=True,
        retraction_reason=None,
        conflict_state=ConflictState.NONE.value,
        medical_safety_state=MedicalSafetyState.PENDING_REVIEW.value,
        normalized_statement=(
            "NIOSH provides workplace safety guidance on occupational noise exposure "
            "and hearing loss prevention for workers."
        ),
        manifest_entity_id=None,
        disease_or_health_condition=None,
        topic_taxonomy=None,
    )
    ok, reason, spec = can_apply_specialized_entity_eligibility(
        source_key=NIOSH_SOURCE_KEY,
        ku=ku,
        canonical_url="https://www.cdc.gov/niosh/topics/noise/",
    )
    assert ok is True, reason
    assert spec is not None and spec.entity_id == "D17"
    # MedlinePlus ALS must not authorize via NIOSH source
    ku.normalized_statement = "Amyotrophic lateral sclerosis motor neuron disease overview."
    ok2, reason2, _ = can_apply_specialized_entity_eligibility(
        source_key=NIOSH_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/amyotrophiclateralsclerosis.html",
    )
    assert ok2 is False


def test_other_candidates_not_in_active_allowlist():
    active = {r["source_key"] for r in active_manifest_rows()}
    # Historical candidate_id names may later become active source_keys when authorized.
    # Hard guarantee: NEEDS_REVIEW / blocked families stay inactive.
    blocked_or_review = {
        "owh_womens_health",
        "cdc_child_development",
        "cdc_ncezid_infectious",
    }
    for row in candidate_rows():
        cid = row["candidate_id"]
        if cid in blocked_or_review or str(row.get("qualification_status")) == "NEEDS_REVIEW":
            assert cid not in active
            assert str(row.get("activation_authorized_this_gate") or "NO").upper() in {"NO", "FALSE"}


def test_registry_file_exists():
    assert Path("backend/config/i5/candidate_qualification_registry_v1.yaml").is_file()
