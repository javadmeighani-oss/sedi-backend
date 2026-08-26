"""Wave02 D01–D17 governed knowledge expansion — offline allowlist/coverage tests."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from backend.app.services.i5.coverage_manifest_loader import load_coverage_manifest
from backend.app.services.i5.trusted_source_manifest import (
    active_manifest_rows,
    governed_low_risk_eligible,
    load_trusted_source_manifest,
)
from backend.app.services.i5.wave02_coverage_identity import resolve_wave02_coverage_from_url


WAVE02_PRODUCT_PRIORITY_MAP = {
    "cardiovascular": "knowledge_domain:cardiovascular",
    "neurology": "parent_taxonomy:neurology (D18/D19 regression)",
    "diabetes/metabolic": "knowledge_domain:diabetes_metabolic",
    "infectious disease": "D13",
    "hepatitis/liver": "D04",
    "psychology/mental health": "knowledge_domain:mental_health_psychology",
    "nutrition": "knowledge_domain:nutrition",
    "exercise": "knowledge_domain:physical_activity_exercise",
    "sleep": "knowledge_domain:lifestyle_prevention_routines",
    "prevention/public health": "knowledge_domain:lifestyle_prevention_routines",
    "lifestyle medicine": "knowledge_domain:lifestyle_prevention_routines",
    "rehabilitation": "D15",
    "healthy aging": "D12",
    "maternal/reproductive": "D10",
    "pediatric": "D11",
    "environmental/occupational": "D17",
    "behavior change": "knowledge_domain:lifestyle_prevention_routines",
    "care/self-care/caregiving": "knowledge_domain:lifestyle_prevention_routines",
}


def test_wave02_allowlist_version_and_four_publishers():
    data = load_trusted_source_manifest()
    assert data["allowlist_version"] == "i5-multisource-v1-wave02"
    assert "WAVE02" in str(data.get("gate_id") or "")
    rows = active_manifest_rows()
    assert len(rows) == 4
    assert governed_low_risk_eligible("nhs_uk_live_well") is True
    assert governed_low_risk_eligible("cdc_health_lifestyle") is True
    assert governed_low_risk_eligible("medlineplus_consumer_health") is False
    assert governed_low_risk_eligible("nimh_nih_mental_health") is False


def test_wave02_urls_match_existing_patterns_no_new_publishers():
    rows = active_manifest_rows()
    for row in rows:
        patterns = [re.compile(p) for p in (row.get("allowed_url_patterns") or [])]
        urls = [row["exact_url"]] + list(row.get("additional_urls") or [])
        assert urls
        for url in urls:
            assert any(p.match(url) for p in patterns), f"{row['source_key']}:{url}"


def test_wave02_d01_d17_authoritative_names_unchanged():
    entities = {e["id"]: e["name_en"] for e in load_coverage_manifest()["entities"]}
    assert entities["D01"] == "Oncology and supportive cancer care"
    assert entities["D13"] == "Infectious diseases beyond hepatitis"
    assert entities["D17"] == "Environmental and occupational health"
    assert "D18" in entities and "D19" in entities


def test_wave02_medlineplus_covers_d01_d16_acquisition_urls():
    row = next(r for r in active_manifest_rows() if r["source_key"] == "medlineplus_consumer_health")
    urls = " ".join([row["exact_url"]] + list(row.get("additional_urls") or [])).lower()
    for needle in (
        "cancers.html",
        "lungdiseases.html",
        "kidneydiseases.html",
        "digestivediseases.html",
        "arthritis.html",
        "skincancer.html",
        "eyediseases.html",
        "hearingdisordersanddeafness.html",
        "dentalhealth.html",
        "womenshealth.html",
        "childrenshealth.html",
        "olderadulthealth.html",
        "infectiousdiseases.html",
        "rarediseases.html",
        "rehabilitation.html",
        "palliativecare.html",
        "amyotrophiclateralsclerosis",
        "multiplesclerosis",
    ):
        assert needle in urls, needle


def test_wave02_nhs_low_risk_expansion_urls_present():
    row = next(r for r in active_manifest_rows() if r["source_key"] == "nhs_uk_live_well")
    urls = " ".join([row["exact_url"]] + list(row.get("additional_urls") or [])).lower()
    for needle in ("healthy-weight", "quit-smoking", "alcohol-advice", "seasonal-health", "eat-well", "exercise"):
        assert needle in urls, needle


def test_wave02_coverage_identity_maps_dxx_and_preserves_lifestyle_for_nhs():
    assert resolve_wave02_coverage_from_url("https://medlineplus.gov/cancers.html").entity_id == "D01"
    assert resolve_wave02_coverage_from_url("https://medlineplus.gov/infectiousdiseases.html").entity_id == "D13"
    nhs = resolve_wave02_coverage_from_url("https://www.nhs.uk/live-well/healthy-weight/")
    assert nhs is not None
    assert nhs.domain == "lifestyle"
    assert nhs.jurisdiction == "GB"


def test_wave02_candidate_gap_list_discovery_only():
    path = Path("backend/config/i5/wave02_candidate_source_gaps_v1.yaml")
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["activation_policy"] == "CANDIDATE_ONLY_NO_RUNTIME"
    cands = data["candidates"]
    assert len(cands) >= 10
    for c in cands:
        assert c["activation"] == "NO"
        assert c["qualification_status"] == "CANDIDATE_ONLY"
        assert c["dxx"].startswith("D")


def test_wave02_priority_map_uses_authoritative_ids():
    entities = {e["id"] for e in load_coverage_manifest()["entities"]}
    assert WAVE02_PRODUCT_PRIORITY_MAP["infectious disease"] in entities
    assert WAVE02_PRODUCT_PRIORITY_MAP["rehabilitation"] in entities
    assert WAVE02_PRODUCT_PRIORITY_MAP["pediatric"] in entities
