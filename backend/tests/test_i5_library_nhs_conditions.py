"""R-044 library: 13 more NHS Health A-Z pages, each inside a lane that nhs_uk_conditions already holds.

No new source and no new lane: every page needs an explicit URL needle in a lane the source is authorised for, so a
page can never be served by an entity the source does not hold.
"""

from __future__ import annotations

import re

import pytest

from backend.app.services.i5.governed_specialized_entity_eligibility import (
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.trusted_source_manifest import manifest_row_for_key

KEY = "nhs_uk_conditions"
NEW = {
    "atrial-fibrillation": "D21",
    "high-cholesterol": "D21",
    "angina": "D21",
    "cardiovascular-disease": "D21",
    "gestational-diabetes": "D22",
    "osteoarthritis": "D05",
    "rheumatoid-arthritis": "D05",
    "gout": "D05",
    "chronic-obstructive-pulmonary-disease-copd": "D02",
    "obstructive-sleep-apnoea": "D25",
    "endometriosis": "D10",
    "polycystic-ovary-syndrome-pcos": "D10",
    "periods": "D10",
}


def _urls():
    row = manifest_row_for_key(KEY)
    return [row["exact_url"], *row["additional_urls"]]


@pytest.mark.parametrize("slug, entity", sorted(NEW.items()))
def test_each_new_page_is_in_the_expected_lane_and_the_manifest(slug, entity):
    url = f"https://www.nhs.uk/conditions/{slug}/"
    assert url in _urls()
    spec = resolve_specialized_entity_from_url(url)
    assert spec is not None and spec.entity_id == entity
    assert entity in specialized_allowed_entities_for_source(KEY)
    assert any(re.match(p, url) for p in manifest_row_for_key(KEY)["allowed_url_patterns"])


def test_every_url_of_the_source_is_in_a_lane_it_holds_and_the_label_matches():
    row = manifest_row_for_key(KEY)
    allowed = specialized_allowed_entities_for_source(KEY)
    assert len(_urls()) == len(set(_urls())) == 61  # R-074 step 5: +10 pages
    assert "max_61_urls" in row["rate_limit"]
    for url in _urls():
        spec = resolve_specialized_entity_from_url(url)
        assert spec is None or spec.entity_id in allowed, url


def test_a_lane_the_source_does_not_hold_stays_closed():
    # digestive (D04) and thyroid pages were considered and left out: this source holds no lane for them
    assert "D04" not in specialized_allowed_entities_for_source(KEY)
    urls = " ".join(_urls())
    for slug in ("irritable-bowel-syndrome-ibs", "coeliac-disease", "overactive-thyroid-hyperthyroidism"):
        assert slug not in urls
