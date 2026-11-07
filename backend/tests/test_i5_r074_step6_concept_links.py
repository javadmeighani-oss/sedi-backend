"""R-074 step 6: knowledge crawled AFTER the concept catalog was written must still be linked to its concept.

Production diagnostics (run 42347768005): the query «caring for a family member with dementia» names the verified concept
«dementia»; retrieval is then restricted to the units linked to that concept (fail-closed concept authority), and only ONE unit
was linked (the other 20+ dementia/Alzheimer's units, crawled in step 5, had no catalog needle) - so the chat got one unit.
Concept identity comes from governed URL needles (no classifier): every new page of an existing concept gets its needle."""
from __future__ import annotations

import io
import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml

from backend.app.services.i5.know02.concept_catalog import concept_key_for_url, load_concept_catalog

ROOT = Path(__file__).resolve().parents[2]
MP = "https://medlineplus.gov/"
NHS = "https://www.nhs.uk/conditions/"

EXPECTED = {
    MP + "dementia.html": "disease:dementia",
    NHS + "vascular-dementia/": "disease:dementia",
    NHS + "frontotemporal-dementia/": "disease:dementia",
    NHS + "dementia/": "disease:dementia",
    MP + "alzheimersdisease.html": "disease:alzheimers",
    MP + "alzheimerscaregivers.html": "disease:alzheimers",
    NHS + "alzheimers-disease/symptoms/": "disease:alzheimers",
    NHS + "alzheimers-disease/treatment/": "disease:alzheimers",
    MP + "highbloodpressure.html": "disease:hypertension",
    MP + "diabeticdiet.html": "disease:diabetes_mellitus",
    MP + "diabetestype2.html": "disease:diabetes_mellitus",
    MP + "diabetescomplications.html": "disease:diabetes_mellitus",
    MP + "backpain.html": "disease:back_pain",
    MP + "sciatica.html": "disease:back_pain",
    NHS + "sciatica/": "disease:back_pain",
    NHS + "slipped-disc/": "disease:back_pain",
    MP + "osteoporosis.html": "disease:osteoporosis",
}


@pytest.mark.parametrize("url,concept", sorted(EXPECTED.items()))
def test_every_new_page_links_to_its_concept(url, concept):
    load_concept_catalog.cache_clear()
    assert concept_key_for_url(url) == concept


def test_pages_without_a_verified_concept_stay_unlinked_and_open():
    # no concept label exists for these topics: the query is not restricted, so they are served by the normal ranking
    for url in (MP + "cholesterol.html", MP + "falls.html", MP + "nutritionforolderadults.html", MP + "muscledisorders.html"):
        assert concept_key_for_url(url) is None


def test_no_previously_mapped_url_changed_concept():
    """Exclusive ownership: every URL of the allowlist keeps the concept it had on main."""
    old_yaml = subprocess.run(
        ["git", "show", "origin/main:backend/config/i5/clinical_concept_catalog_v1.yaml"], capture_output=True, cwd=ROOT
    ).stdout.decode("utf-8")
    if not old_yaml.strip():
        pytest.skip("origin/main not available")
    old = yaml.safe_load(old_yaml)

    def mapping(cat, url):
        sample = url.casefold()
        for c in cat.get("concepts") or []:
            if any(str(n).casefold() in sample for n in c.get("url_needles") or []):
                return c["concept_key"]
        return None

    allow = yaml.safe_load((ROOT / "backend/config/i5/multisource_activation_allowlist_v1.yaml").read_text(encoding="utf-8"))
    urls = []
    for v in allow.values():
        if isinstance(v, list) and v and isinstance(v[0], dict) and "source_key" in v[0]:
            for s in v:
                urls += [s["exact_url"]] + list(s.get("additional_urls") or [])
    new = yaml.safe_load((ROOT / "backend/config/i5/clinical_concept_catalog_v1.yaml").read_text(encoding="utf-8"))
    changed = [(u, mapping(old, u), mapping(new, u)) for u in urls if mapping(old, u) not in (None, mapping(new, u))]
    assert changed == []


def test_the_catalog_still_loads_with_unique_keys_and_verified_labels():
    load_concept_catalog.cache_clear()
    cat = load_concept_catalog()
    keys = [c["concept_key"] for c in cat["concepts"]]
    assert len(keys) == len(set(keys)) == 28
