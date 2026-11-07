"""R-074 step 5: the weak knowledge areas (muscle/joint injuries and back pain, dementia, diabetes care and diet, blood pressure and
cholesterol, falls) get more open-licence pages (MedlinePlus public domain, NHS OGL) in the lanes that already exist.

Same rules as R-046: no new lane, no gate loosened; a page is served only by the entity its URL names; exclusive ownership (no
previously allowlisted URL changed lane, no URL listed twice); the weekly rate limit equals the URL count."""
from __future__ import annotations

import re
from collections import Counter

import pytest

from backend.app.services.i5.governed_specialized_entity_eligibility import (
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.trusted_source_manifest import active_manifest_rows, manifest_row_for_key
from backend.app.services.i5.wave02_coverage_identity import resolve_wave02_coverage_from_url

MP = "https://medlineplus.gov/"
NHS = "https://www.nhs.uk/conditions/"
EXPECTED = {
    "D05": [MP + f"{n}.html" for n in (
        "backpain", "neckinjuriesanddisorders", "shoulderinjuriesanddisorders", "kneeinjuriesanddisorders", "hipinjuriesanddisorders",
        "elbowinjuriesanddisorders", "wristinjuriesanddisorders", "footinjuriesanddisorders", "sprainsandstrains", "muscledisorders",
        "osteoporosis", "osteoarthritis", "sciatica")]
    + [NHS + f"{n}/" for n in ("sprains-and-strains", "sciatica", "tennis-elbow", "frozen-shoulder", "plantar-fasciitis", "slipped-disc")],
    "D24": [MP + "alzheimersdisease.html", MP + "dementia.html", NHS + "alzheimers-disease/symptoms/",
            NHS + "alzheimers-disease/treatment/", NHS + "vascular-dementia/", NHS + "frontotemporal-dementia/"],
    "D22": [MP + "diabetestype2.html", MP + "diabeticdiet.html", MP + "diabetescomplications.html"],
    "D21": [MP + "highbloodpressure.html", MP + "cholesterol.html"],
}
CASES = [(ent, url) for ent, urls in EXPECTED.items() for url in urls]


@pytest.mark.parametrize("entity,url", CASES)
def test_each_new_page_resolves_to_its_reviewed_lane(entity, url):
    spec = resolve_specialized_entity_from_url(url)
    assert spec is not None and spec.entity_id == entity


def _row_urls(key):
    row = manifest_row_for_key(key)
    return [row["exact_url"], *(row.get("additional_urls") or [])]


def test_pages_are_in_the_right_sources_and_the_lanes_are_active():
    mp = set(_row_urls("medlineplus_consumer_health"))
    nhs = set(_row_urls("nhs_uk_conditions"))
    for ent, url in CASES:
        assert url in (nhs if url.startswith(NHS) else mp), url
    for ent in ("D05", "D21", "D22", "D24"):
        assert ent in specialized_allowed_entities_for_source("medlineplus_consumer_health")
        assert ent in specialized_allowed_entities_for_source("nhs_uk_conditions")


def test_rate_limits_equal_the_url_counts_and_no_url_is_listed_twice():
    seen = Counter()
    for row in active_manifest_rows():
        urls = [row["exact_url"], *(row.get("additional_urls") or [])]
        seen.update(urls)
        if row["source_key"] in ("medlineplus_consumer_health", "nhs_uk_conditions", "medlineplus_eldercare"):
            assert row["rate_limit"] == f"weekly_controlled_max_{len(urls)}_urls", row["source_key"]
    assert [u for u, n in seen.items() if n > 1] == []


def test_falls_is_elder_care_in_the_low_risk_source_with_both_guards():
    row = manifest_row_for_key("medlineplus_eldercare")
    assert MP + "falls.html" in row["additional_urls"]
    assert any(re.match(p, MP + "falls.html") for p in row["allowed_url_patterns"])
    assert row["reject_resource_lists"] is True and row["reject_medicine_talk"] is True
    ident = resolve_wave02_coverage_from_url(MP + "falls.html")
    assert ident.topic == "elder_care"


def test_the_pages_are_open_licence_only():
    assert manifest_row_for_key("medlineplus_consumer_health")["rights_terms_state"] == "PUBLIC_DOMAIN"
    assert manifest_row_for_key("nhs_uk_conditions")["rights_terms_state"] == "OGL"
