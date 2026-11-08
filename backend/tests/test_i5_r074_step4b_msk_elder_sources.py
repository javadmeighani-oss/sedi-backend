"""R-074 step 4b: more reviewed musculoskeletal / physiotherapy / elder-care pages in the EXISTING lanes (no gate loosened)."""
from __future__ import annotations

import re

from backend.app.services.i5.governed_specialized_entity_eligibility import (
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.know02.concept_catalog import load_concept_catalog
from backend.app.services.i5.wave02_coverage_identity import resolve_wave02_coverage_from_url
from backend.app.services.i5.trusted_source_manifest import manifest_row_for_key

MP = "https://medlineplus.gov/"
MSK = ("backinjuries", "fibromyalgia", "gout", "jointdisorders", "rheumatoidarthritis", "rotatorcuffinjuries", "sportsinjuries")
ELDER = ("seniorshealth", "balanceproblems", "caregivers", "exerciseforseniors")


def _urls(key):
    row = manifest_row_for_key(key)
    return [row["exact_url"], *(row.get("additional_urls") or [])]


def test_musculoskeletal_pages_are_in_the_source_and_resolve_to_the_msk_lane():
    urls = set(_urls("medlineplus_consumer_health"))
    allowed = specialized_allowed_entities_for_source("medlineplus_consumer_health")
    assert "D05" in allowed
    for slug in MSK:
        assert f"{MP}{slug}.html" in urls
        spec = resolve_specialized_entity_from_url(f"{MP}{slug}.html")
        assert spec is not None and spec.entity_id == "D05", slug


def test_the_nhs_source_was_not_widened_to_the_rehabilitation_lane():
    """The NHS physiotherapy page was NOT added: nhs_uk_conditions does not hold D15, and widening a source's lanes would loosen a gate."""
    assert "D15" not in specialized_allowed_entities_for_source("nhs_uk_conditions")
    assert "https://www.nhs.uk/conditions/physiotherapy/" not in set(_urls("nhs_uk_conditions"))


def test_elder_care_pages_are_in_the_source_pattern_and_carry_the_elder_care_identity():
    row = manifest_row_for_key("medlineplus_eldercare")
    urls = set(_urls("medlineplus_eldercare"))
    pattern = re.compile(row["allowed_url_patterns"][0])
    assert "max_11_urls" in row["rate_limit"] and len(urls) == 11
    for slug in ELDER:
        u = f"{MP}{slug}.html"
        assert u in urls and pattern.match(u), slug
        ident = resolve_wave02_coverage_from_url(u)
        assert ident is not None and ident.topic == "elder_care", slug
    assert not pattern.match(f"{MP}depression.html")  # the pattern did not widen to other topics


def test_no_gate_was_loosened_the_sources_keep_their_rights_and_robots_state():
    for key in ("medlineplus_eldercare", "medlineplus_consumer_health", "nhs_uk_conditions"):
        row = manifest_row_for_key(key)
        assert row["robots_access_state"] == "ALLOWED" and row["rights_terms_state"] in {"PUBLIC_DOMAIN", "OGL"}


def test_new_pages_are_linked_to_their_concepts_for_retrieval():
    cat = load_concept_catalog()
    concepts = {c["concept_key"]: c for c in cat["concepts"]}
    assert "medlineplus.gov/backinjuries" in concepts["disease:back_pain"]["url_needles"]
    assert "medlineplus.gov/exerciseforseniors" in concepts["topic:physical_activity"]["url_needles"]
