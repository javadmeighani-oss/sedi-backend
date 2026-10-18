"""New NHS pages (mental health, cancer, kidney, asthma, menopause, pregnancy) map to the right entity and are controlled."""
import pytest

from backend.app.services.i5.governed_specialized_entity_eligibility import resolve_specialized_entity_from_url
from backend.app.services.i5.multisource_activation import active_allowlist_rows

CASES = {
    "https://www.nhs.uk/mental-health/conditions/depression-in-adults/": "D23",
    "https://www.nhs.uk/mental-health/conditions/panic-disorder/": "D23",
    "https://www.nhs.uk/mental-health/feelings-symptoms-behaviours/feelings-and-symptoms/stress/": "D23",
    "https://www.nhs.uk/tests-and-treatments/cognitive-behavioural-therapy-cbt/": "D23",
    "https://www.nhs.uk/conditions/breast-cancer-in-women/": "D01",
    "https://www.nhs.uk/conditions/prostate-cancer/": "D01",
    "https://www.nhs.uk/conditions/bowel-cancer/": "D01",
    "https://www.nhs.uk/conditions/kidney-disease/": "D03",
    "https://www.nhs.uk/conditions/asthma/": "D02",
    "https://www.nhs.uk/conditions/menopause-and-perimenopause/": "D10",
    "https://www.nhs.uk/pregnancy/keeping-well/have-a-healthy-diet/": "D10",
    "https://www.nhs.uk/conditions/iron-deficiency-anaemia/": "D26",
    "https://www.nhs.uk/conditions/vitamin-b12-or-folate-deficiency-anaemia/": "D26",
    "https://www.nhs.uk/conditions/enlarged-prostate/": "D27",
    "https://www.nhs.uk/conditions/erection-problems-erectile-dysfunction/": "D27",
    "https://www.nhs.uk/conditions/testicular-cancer/": "D27",
    "https://womenshealth.gov/pregnancy": "D10",
}


@pytest.mark.parametrize("url,entity", CASES.items())
def test_url_maps_to_expected_entity(url, entity):
    spec = resolve_specialized_entity_from_url(url)
    assert spec is not None and spec.entity_id == entity


def test_new_urls_are_in_the_controlled_allowlist_and_match_patterns():
    import re

    rows = {r["source_key"]: r for r in active_allowlist_rows()}
    for key, urls in {
        "nhs_uk_mental_health": [u for u in CASES if "mental-health" in u or "tests-and-treatments" in u],
        "nhs_uk_conditions": [u for u in CASES if u.startswith("https://www.nhs.uk/conditions/") or "/pregnancy/" in u],
    }.items():
        row = rows[key]
        controlled = [row["exact_url"], *row.get("additional_urls", [])]
        pats = [re.compile(p) for p in row["allowed_url_patterns"]]
        for u in urls:
            assert u in controlled, (key, u)
            assert any(p.match(u) for p in pats), (key, u)
    assert len(rows) == 21


def test_agency_self_description_headings_are_boilerplate_but_guidance_is_not():
    from backend.app.services.i5.conceptual_extraction import _BOILERPLATE_SECTION_HEADINGS as R

    for h in ("What CDC is doing", "About us", "Partners", "Our work"):
        assert R.match(h), h
    for h in ("Treatment for MND", "How much activity do adults need?", "Symptoms", "Why it matters"):
        assert not R.match(h), h


def test_arabic_chest_pain_and_breathing_difficulty_are_terminal_emergencies():
    from backend.app.services.intelligence.safety_risk import assess_safety_risk, requires_terminal_safety_response

    for msg in ("ألم شديد في الصدر وضيق في التنفس", "أعاني من ألم في الصدر", "لدي صعوبة في التنفس"):
        assert requires_terminal_safety_response(assess_safety_risk(message=msg, language="ar")), msg
    for msg in ("كيف أتعامل مع القلق وقلة النوم؟", "ما هو مرض التصلب الجانبي الضموري"):
        assert not requires_terminal_safety_response(assess_safety_risk(message=msg, language="ar")), msg


def test_disease_labels_are_founder_approved_and_broad_topics_stay_drafts():
    from backend.app.services.i5.know02.concept_catalog import load_concept_catalog

    for concept in load_concept_catalog()["concepts"]:
        for label in concept["labels"]:
            if label["language"] == "en":
                continue
            if concept["concept_key"].startswith("disease:"):
                assert label["status"] == "FOUNDER_APPROVED" and label.get("approved_on") == "2026-10-18", (concept["concept_key"], label)
            else:
                assert label["status"] == "MODEL_ASSISTED_DRAFT", (concept["concept_key"], label)
