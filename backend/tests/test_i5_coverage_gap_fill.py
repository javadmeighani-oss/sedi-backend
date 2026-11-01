"""R-046 coverage: weak domains get more MedlinePlus topics (public domain), each in the lane its URL names.

No new lane: a page is served only by the entity its URL needle names and only when medlineplus_consumer_health holds
that entity. Elder care is a separate low-risk source with the resource-list and medicine guards.
"""

from __future__ import annotations

import re

import pytest

from backend.app.services.i5.governed_specialized_entity_eligibility import (
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.trusted_source_manifest import active_manifest_rows, governed_low_risk_eligible, manifest_row_for_key
from backend.app.services.i5.wave02_coverage_identity import resolve_wave02_coverage_from_url

MP = "https://medlineplus.gov/"
KEY = "medlineplus_consumer_health"
ELDER = "medlineplus_eldercare"
SAMPLES = {
    "D01": ["breastcancer", "colorectalcancer", "prostatecancer"],
    "D03": ["chronickidneydisease", "kidneystones"],
    "D04": ["celiacdisease", "crohnsdisease", "gerd"],
    "D13": ["hepatitisb", "hepatitisc", "hiv"],
    "D11": ["childdevelopment", "parenting"],
    "D15": ["rehabilitation", "strokerehabilitation"],
    "D16": ["endoflifeissues", "hospicecare"],
    "D06": ["acne", "eczema", "psoriasis"],
}


def _urls(key):
    row = manifest_row_for_key(key)
    return [row["exact_url"], *row["additional_urls"]]


@pytest.mark.parametrize("lane, slugs", sorted(SAMPLES.items()))
def test_new_topics_are_in_the_manifest_and_resolve_to_their_lane(lane, slugs):
    assert lane in specialized_allowed_entities_for_source(KEY)
    for slug in slugs:
        url = f"{MP}{slug}.html"
        assert url in _urls(KEY), url
        spec = resolve_specialized_entity_from_url(url)
        assert spec is not None and spec.entity_id == lane, url


def test_no_page_is_listed_by_two_sources_and_all_match_the_patterns():
    seen: dict[str, str] = {}
    for row in active_manifest_rows():
        for url in [row["exact_url"], *(row.get("additional_urls") or [])]:
            key = url.rstrip("/").lower()
            assert key not in seen, (url, seen.get(key), row["source_key"])
            seen[key] = row["source_key"]
    for key in (KEY, ELDER):
        patterns = [re.compile(p) for p in manifest_row_for_key(key)["allowed_url_patterns"]]
        for url in _urls(key):
            assert any(p.match(url) for p in patterns), (key, url)


def test_every_medlineplus_url_resolves_to_a_lane_the_source_holds_or_none():
    allowed = specialized_allowed_entities_for_source(KEY)
    for url in _urls(KEY):
        spec = resolve_specialized_entity_from_url(url)
        assert spec is None or spec.entity_id in allowed, url


def test_the_rate_limit_label_matches_the_url_count():
    for key in (KEY, ELDER):
        assert f"max_{len(_urls(key))}_urls" in manifest_row_for_key(key)["rate_limit"], key


def test_pages_that_belong_to_other_lanes_were_left_out():
    urls = " ".join(_urls(KEY))
    assert "childdentalhealth" not in urls  # dental lane (D09) owns it
    assert "copingwithchronicillness" not in urls  # psychology lane (D23) owns it


def test_elder_care_is_a_low_risk_source_with_both_guards_and_no_specialized_lane():
    row = manifest_row_for_key(ELDER)
    assert governed_low_risk_eligible(ELDER) is True and row["rights_terms_state"] == "PUBLIC_DOMAIN"
    assert row["reject_resource_lists"] is True and row["reject_medicine_talk"] is True
    for url in _urls(ELDER):
        assert resolve_specialized_entity_from_url(url) is None, url
        cov = resolve_wave02_coverage_from_url(url)
        assert cov is not None and cov.topic == "elder_care", url
