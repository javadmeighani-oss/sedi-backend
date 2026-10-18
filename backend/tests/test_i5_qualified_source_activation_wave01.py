"""Qualified NIH family activation + specialized D01–D07/D09/D16 serving — offline tests."""
from __future__ import annotations

import re

from backend.app.services.i5.candidate_qualification_registry import candidate_rows
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.trusted_source_manifest import (
    active_manifest_rows,
    governed_low_risk_eligible,
    load_trusted_source_manifest,
)

AUTHORIZED_NEW = {
    "nci_cancer_gov",
    "nhlbi_health",
    "niddk_health",
    "niams_health",
    "nei_eye_health",
    "nidcr_oral_health",
}
COVERAGE_CLOSURE = {
    "nidcd_hearing_balance",
    "owh_womens_health",
    "cdc_child_development",
    "cdc_ncezid_infectious",
    "gard_rare_diseases",
    "nichd_rehabilitation",
}
WHO_INACTIVE = {"who_fact_sheets"}


def test_allowlist_wave01_qualified_activation_version_and_count():
    data = load_trusted_source_manifest()
    assert str(data["allowlist_version"]).startswith("i5-multisource-v1")
    rows = active_manifest_rows()
    keys = {r["source_key"] for r in rows}
    assert len(rows) == 21
    assert AUTHORIZED_NEW.issubset(keys)
    assert COVERAGE_CLOSURE.issubset(keys)
    assert not (keys & WHO_INACTIVE)
    for key in AUTHORIZED_NEW | COVERAGE_CLOSURE:
        assert governed_low_risk_eligible(key) is False


def test_authorized_family_urls_match_patterns():
    by_key = {r["source_key"]: r for r in active_manifest_rows()}
    for key in AUTHORIZED_NEW:
        row = by_key[key]
        patterns = [re.compile(p) for p in (row.get("allowed_url_patterns") or [])]
        urls = [row["exact_url"]] + list(row.get("additional_urls") or [])
        assert urls
        for url in urls:
            assert any(p.match(url) for p in patterns), f"{key}:{url}"
        assert row["rights_terms_state"] == "PUBLIC_DOMAIN"
        assert row["robots_access_state"] == "ALLOWED"
        assert row.get("specialized_serving_eligibility")


def test_specialized_url_identity_map():
    assert resolve_specialized_entity_from_url(
        "https://www.cancer.gov/publications/pdq"
    ).entity_id == "D01"
    assert resolve_specialized_entity_from_url(
        "https://www.cancer.gov/about-cancer/advanced-cancer/care-choices"
    ).entity_id == "D16"
    assert resolve_specialized_entity_from_url(
        "https://www.nhlbi.nih.gov/health/asthma"
    ).entity_id == "D02"
    assert resolve_specialized_entity_from_url(
        "https://www.niddk.nih.gov/health-information/kidney-disease"
    ).entity_id == "D03"
    assert resolve_specialized_entity_from_url(
        "https://www.niddk.nih.gov/health-information/liver-disease"
    ).entity_id == "D04"
    assert resolve_specialized_entity_from_url(
        "https://www.niams.nih.gov/health-topics/arthritis"
    ).entity_id == "D05"
    assert resolve_specialized_entity_from_url(
        "https://www.niams.nih.gov/health-topics/skin-diseases"
    ).entity_id == "D06"
    assert resolve_specialized_entity_from_url(
        "https://www.nei.nih.gov/learn-about-eye-health"
    ).entity_id == "D07"
    assert resolve_specialized_entity_from_url(
        "https://www.nidcr.nih.gov/health-info/oral-hygiene"
    ).entity_id == "D09"


def test_specialized_entities_bound_to_source_families():
    assert specialized_allowed_entities_for_source("nci_cancer_gov") == {"D01", "D16"}
    assert specialized_allowed_entities_for_source("nhlbi_health") == {"D02", "D21"}  # D-010 heart
    assert specialized_allowed_entities_for_source("niddk_health") == {"D03", "D04", "D22"}  # D-010 diabetes
    assert specialized_allowed_entities_for_source("niams_health") == {"D05", "D06"}
    assert specialized_allowed_entities_for_source("nei_eye_health") == {"D07"}
    assert specialized_allowed_entities_for_source("nidcr_oral_health") == {"D09"}
    # Regression preserved
    assert specialized_allowed_entities_for_source("niosh_occupational") == {"D17"}
    assert "D18" in specialized_allowed_entities_for_source("medlineplus_consumer_health")
    assert "D19" in specialized_allowed_entities_for_source("medlineplus_consumer_health")


def test_who_remains_inactive_and_registry_activation_no():
    active = {r["source_key"] for r in active_manifest_rows()}
    assert "who_fact_sheets" not in active
    for row in candidate_rows():
        assert str(row["activation"]).upper() in {"NO", "FALSE"}


# --- D-010 knowledge breadth (neurology, chronic disease, mental health, lifestyle) ---------

BREADTH_SPECIALIZED = {
    "nhs_uk_conditions": {"D01", "D02", "D03", "D05", "D10", "D18", "D19", "D21", "D22", "D24", "D25", "D26", "D27"},
    "nhs_uk_mental_health": {"D23"},
    "cdc_chronic_disease": {"D10", "D18", "D21", "D22", "D23", "D24", "D25"},
}
BREADTH_LOW_RISK = {"nccih_mind_body"}
# URLs that were already in the manifest before D-010 and are intentionally not
# specialized-served (hub pages / D23 depression URL boundary).
PRE_EXISTING_UNSPECIALIZED = {
    "https://medlineplus.gov/olderadulthealth.html",
    "https://medlineplus.gov/healthyliving.html",
    "https://www.nimh.nih.gov/health/topics/depression",
}


def test_breadth_sources_are_governed_and_every_url_is_served_by_its_authority():
    from backend.app.services.i5.governed_low_risk_eligibility import domain_is_recognized_low_risk
    from backend.app.services.i5.wave02_coverage_identity import resolve_wave02_coverage_from_url

    rows = {r["source_key"]: r for r in active_manifest_rows()}
    assert BREADTH_SPECIALIZED.keys() | BREADTH_LOW_RISK <= rows.keys()
    for key, entities in BREADTH_SPECIALIZED.items():
        assert governed_low_risk_eligible(key) is False
        assert specialized_allowed_entities_for_source(key) == entities
    for key in BREADTH_LOW_RISK:
        assert governed_low_risk_eligible(key) is True

    for key, row in rows.items():
        assert row["rights_terms_state"] in {"OGL", "PUBLIC_DOMAIN"}
        assert row["robots_access_state"] == "ALLOWED"
        patterns = [re.compile(p) for p in row["allowed_url_patterns"]]
        urls = [row["exact_url"], *(row.get("additional_urls") or [])]
        assert len(urls) == len(set(urls)), key
        low_risk = governed_low_risk_eligible(key)
        for url in urls:
            assert any(p.match(url) for p in patterns), (key, url)
            spec = resolve_specialized_entity_from_url(url)
            if low_risk:
                cov = resolve_wave02_coverage_from_url(url)
                domain = spec.domain if spec else (cov.domain if cov else "lifestyle")
                assert domain_is_recognized_low_risk(domain), (key, url, domain)
            elif url not in PRE_EXISTING_UNSPECIALIZED:
                assert spec is not None, (key, url)
                assert spec.entity_id in specialized_allowed_entities_for_source(key), (key, url)


def test_breadth_neurology_and_cardiometabolic_url_identity():
    expected = {
        "https://www.nhs.uk/conditions/motor-neurone-disease/": "D18",
        "https://medlineplus.gov/genetics/condition/amyotrophic-lateral-sclerosis/": "D18",
        "https://www.cdc.gov/als/": "D18",
        "https://www.nhs.uk/conditions/multiple-sclerosis/": "D19",
        "https://www.nhs.uk/conditions/parkinsons-disease/": "D24",
        "https://www.nhs.uk/conditions/epilepsy/": "D24",
        "https://www.cdc.gov/stroke/about/index.html": "D24",
        "https://www.nhlbi.nih.gov/health/high-blood-pressure": "D21",  # not D02 (nhlbi hub)
        "https://www.nhlbi.nih.gov/health/asthma": "D02",
        "https://www.niddk.nih.gov/health-information/diabetes/overview/what-is-diabetes": "D22",
        "https://www.nhs.uk/mental-health/conditions/generalised-anxiety-disorder-gad/": "D23",
        "https://www.nhs.uk/conditions/insomnia/": "D25",
    }
    for url, entity in expected.items():
        spec = resolve_specialized_entity_from_url(url)
        assert spec is not None and spec.entity_id == entity, (url, spec)
