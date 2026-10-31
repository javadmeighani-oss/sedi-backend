"""R-044 principle 2: new psychology / wellbeing pages enter ONLY through the D23 fail-closed boundary.

Everyday emotional-support topics (grief, anger, low mood, self-esteem, loneliness, work stress / burnout, anxiety,
stress, mindfulness, CBT self-help, sleep, change, talking about mental health, being active, coping after trauma) were
missing. They are added as manifest URLs of existing sources (no new source, no new scheduler). The low-risk path has
no crisis / medication phrase check, so these pages deliberately do NOT use it.
"""

from __future__ import annotations

import re

import pytest

from backend.app.services.i5.governed_specialized_entity_eligibility import (
    _d23_mh_edu_content_blocked,
    content_quality_pass,
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.trusted_source_manifest import active_manifest_rows

NHS_FEELINGS = "https://www.nhs.uk/mental-health/feelings-symptoms-behaviours/feelings-and-symptoms/"
NHS_EMM = "https://www.nhs.uk/every-mind-matters/"
NEW_URLS = {
    "nhs_uk_mental_health": [
        NHS_FEELINGS + "grief-bereavement-loss/",
        NHS_FEELINGS + "anger/",
        NHS_FEELINGS + "low-mood-sadness-depression/",
        "https://www.nhs.uk/mental-health/self-help/tips-and-support/raise-low-self-esteem/",
        NHS_EMM + "lifes-challenges/loneliness/",
        NHS_EMM + "lifes-challenges/work-related-stress/",
        NHS_EMM + "mental-health-issues/anxiety/",
        NHS_EMM + "mental-health-issues/stress/",
        NHS_EMM + "mental-health-issues/low-mood/",
        NHS_EMM + "mental-wellbeing-tips/self-help-cbt-techniques/",
        NHS_EMM + "mental-wellbeing-tips/what-is-mindfulness/",
        NHS_EMM + "mental-wellbeing-tips/how-to-meditate-for-beginners/",
        NHS_EMM + "mental-wellbeing-tips/top-tips-to-improve-your-mental-wellbeing/",
        NHS_EMM + "mental-wellbeing-tips/how-to-fall-asleep-faster-and-sleep-better/",
        NHS_EMM + "mental-wellbeing-tips/how-to-deal-with-change/",
        NHS_EMM + "mental-wellbeing-tips/how-to-talk-about-your-mental-health/",
        NHS_EMM + "mental-wellbeing-tips/be-active-for-your-mental-health/",
    ],
    "nimh_nih_mental_health": ["https://www.nimh.nih.gov/health/topics/coping-with-traumatic-events"],
    "cdc_chronic_disease": [
        "https://www.cdc.gov/emotional-well-being/managing-difficult-emotions/index.html",
        "https://www.cdc.gov/emotional-well-being/improve-your-emotional-well-being/index.html",
        "https://www.cdc.gov/mental-health/living-with/index.html",
    ],
}
ALL_NEW = [u for urls in NEW_URLS.values() for u in urls]

GOOD = (
    "Loneliness can affect your mental health and wellbeing. Try to stay connected with people you trust, join a "
    "local group or volunteer, and make small regular plans to see someone each week."
)
UK_ROUTE = (
    "If you feel you cannot cope, call 999 or contact Samaritans on 116 123 for emotional support. Loneliness can "
    "affect your mental health and wellbeing, so stay connected with people you trust."
)
CRISIS = (
    "Loneliness can affect your mental health and wellbeing. Some people have thoughts of suicide when they feel "
    "alone for a long time, so stay connected with people you trust."
)


def _rows():
    return {r["source_key"]: r for r in active_manifest_rows()}


@pytest.mark.parametrize("url", ALL_NEW)
def test_every_new_page_resolves_to_the_d23_mental_health_education_entity(url):
    spec = resolve_specialized_entity_from_url(url)
    assert spec is not None, url
    assert spec.entity_id == "D23"
    assert spec.domain == "mental_health_psychology"


def test_new_pages_are_in_the_right_existing_sources_and_match_their_patterns():
    rows = _rows()
    for key, urls in NEW_URLS.items():
        row = rows[key]
        listed = [row["exact_url"], *(row.get("additional_urls") or [])]
        patterns = [re.compile(p) for p in row["allowed_url_patterns"]]
        assert "D23" in specialized_allowed_entities_for_source(key)
        for url in urls:
            assert url in listed, (key, url)
            assert any(p.match(url) for p in patterns), (key, url)
        assert len(listed) == len(set(listed))


def test_no_new_source_and_the_low_risk_source_is_untouched():
    rows = _rows()
    assert len(rows) == 21
    live_well = rows["nhs_uk_live_well"]
    assert len([live_well["exact_url"], *live_well["additional_urls"]]) == 23
    assert not any("every-mind-matters" in u for u in live_well["additional_urls"])
    assert sum(1 + len(r.get("additional_urls") or []) for r in rows.values()) == 189


def test_rate_limit_labels_of_the_changed_sources_match_their_url_counts():
    for key in NEW_URLS:
        row = _rows()[key]
        n = 1 + len(row["additional_urls"])
        assert f"max_{n}_urls" in str(row["rate_limit"]), key


@pytest.mark.parametrize("url", [NHS_EMM + "lifes-challenges/loneliness/", NHS_FEELINGS + "grief-bereavement-loss/"])
def test_good_education_text_passes_on_the_new_pages(url):
    ok, reason = content_quality_pass(GOOD, resolve_specialized_entity_from_url(url), canonical_url=url)
    assert ok, reason


@pytest.mark.parametrize("url", [NHS_EMM + "lifes-challenges/loneliness/", "https://www.cdc.gov/emotional-well-being/managing-difficult-emotions/index.html"])
def test_uk_crisis_routes_fail_closed_on_the_new_pages(url):
    spec = resolve_specialized_entity_from_url(url)
    ok, reason = content_quality_pass(UK_ROUTE, spec, canonical_url=url)
    assert not ok
    assert reason == "MH_EDU_UK_CRISIS_ROUTE_BLOCK"


def test_the_existing_crisis_boundary_still_blocks_on_the_new_pages():
    url = NHS_EMM + "lifes-challenges/loneliness/"
    ok, reason = content_quality_pass(CRISIS, resolve_specialized_entity_from_url(url), canonical_url=url)
    assert not ok
    assert reason == "MH_EDU_BOUNDARY_BLOCK"


def test_the_uk_route_rule_does_not_re_judge_pages_that_were_already_in_scope():
    url = "https://www.nhs.uk/mental-health/conditions/panic-disorder/"
    spec = resolve_specialized_entity_from_url(url)
    assert _d23_mh_edu_content_blocked(UK_ROUTE, spec, canonical_url=url) == (False, "")
