"""Wave01 governed knowledge expansion — allowlist scope + coverage matrix (offline)."""
from __future__ import annotations

import re
from pathlib import Path

from backend.app.services.i5.coverage_manifest_loader import load_coverage_manifest
from backend.app.services.i5.trusted_source_manifest import (
    active_manifest_rows,
    governed_low_risk_eligible,
    load_trusted_source_manifest,
)


# Authoritative D01–D19 names from coverage_manifest_v1.yaml (do not invent).
WAVE01_PRODUCT_PRIORITY_MAP = {
    "ALS": "D18",
    "MS": "D19",
    "cardiovascular": "knowledge_domain:cardiovascular",
    "neurology": "parent_taxonomy:neurology (D18/D19)",
    "diabetes/metabolic": "knowledge_domain:diabetes_metabolic",
    "mental health": "knowledge_domain:mental_health_psychology",
    "nutrition": "knowledge_domain:nutrition",
    "exercise": "knowledge_domain:physical_activity_exercise",
    "sleep": "knowledge_domain:lifestyle_prevention_routines",
    "prevention/public health": "knowledge_domain:lifestyle_prevention_routines",
}


def test_wave01_allowlist_urls_match_patterns_and_no_new_publishers():
    rows = active_manifest_rows()
    assert len(rows) == 4
    keys = {r["source_key"] for r in rows}
    assert keys == {
        "nhs_uk_live_well",
        "medlineplus_consumer_health",
        "cdc_health_lifestyle",
        "nimh_nih_mental_health",
    }
    for row in rows:
        patterns = [re.compile(p) for p in (row.get("allowed_url_patterns") or [])]
        assert patterns, row["source_key"]
        urls = [row["exact_url"]] + list(row.get("additional_urls") or [])
        for url in urls:
            assert any(p.match(url) for p in patterns), f"{row['source_key']}:{url}"
            assert url.startswith("https://")


def test_wave01_als_ms_mapped_to_medlineplus_only_among_active():
    data = load_coverage_manifest()
    sm = data["source_mapping"]
    assert sm["D18"] == ["medlineplus_consumer_health"]
    assert sm["D19"] == ["medlineplus_consumer_health"]
    assert governed_low_risk_eligible("medlineplus_consumer_health") is False
    # Acquisition in-scope; auto-ELIGIBLE out-of-scope for MedlinePlus (SOURCE_SCOPE for serving).
    row = next(r for r in active_manifest_rows() if r["source_key"] == "medlineplus_consumer_health")
    urls = " ".join([row["exact_url"]] + list(row.get("additional_urls") or [])).lower()
    assert "amyotrophiclateralsclerosis" in urls
    assert "multiplesclerosis" in urls


def test_wave01_low_risk_publishers_cover_nutrition_exercise_prevention():
    by_key = {r["source_key"]: r for r in active_manifest_rows()}
    assert governed_low_risk_eligible("nhs_uk_live_well") is True
    assert governed_low_risk_eligible("cdc_health_lifestyle") is True
    nhs_urls = " ".join(
        [by_key["nhs_uk_live_well"]["exact_url"]]
        + list(by_key["nhs_uk_live_well"].get("additional_urls") or [])
    )
    assert "eat-well" in nhs_urls
    assert "exercise" in nhs_urls
    cdc_urls = " ".join(
        [by_key["cdc_health_lifestyle"]["exact_url"]]
        + list(by_key["cdc_health_lifestyle"].get("additional_urls") or [])
    )
    assert "healthyliving" in cdc_urls


def test_wave01_manifest_version_and_gate_marker():
    data = load_trusted_source_manifest()
    assert data["allowlist_version"] == "i5-multisource-v1-wave01"
    assert data.get("gate_id") == "PD-I5-V1-D01-D19-GOVERNED-KNOWLEDGE-EXPANSION-WAVE01-01"
    assert Path("backend/config/i5/multisource_activation_allowlist_v1.yaml").is_file()


def test_wave01_priority_map_uses_authoritative_dxx():
    entities = {e["id"]: e for e in load_coverage_manifest()["entities"]}
    assert entities["D18"]["alias"] == "ALS"
    assert entities["D19"]["alias"] == "MS"
    assert WAVE01_PRODUCT_PRIORITY_MAP["ALS"] == "D18"
    assert WAVE01_PRODUCT_PRIORITY_MAP["MS"] == "D19"
    # D01–D17 names must remain broad-domain family labels from authority.
    assert "Oncology" in entities["D01"]["name_en"]
