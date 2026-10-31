"""R-044 step 2: MedlinePlus psychology feed = the "Mental Health and Behavior" group page read by link discovery.

robots.txt disallows the MedlinePlus XML files and topic/group RSS feeds, and the Web Service host has no robots.txt
(the Gate3 robots check fails closed on it), so the governed feed is the group page. A topic is kept only when it is
one of the reviewed D23 MedlinePlus pages. New D23 pages also fail closed on US crisis routes, medicine talk and lists
of outside resources; pages that were eligible before R-044 are not re-judged.
"""

from __future__ import annotations

import copy
from urllib import robotparser

import pytest

from backend.app.services.i5 import link_discovery as ld
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    _d23_mh_edu_content_blocked,
    content_quality_pass,
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.trusted_source_manifest import manifest_row_for_key

MP = "https://medlineplus.gov/"
HUB = MP + "mentalhealthandbehavior.html"
REVIEWED = (
    "anxiety",
    "bereavement",
    "childmentalhealth",
    "copingwithchronicillness",
    "copingwithdisasters",
    "depression",
    "howtoimprovementalhealth",
    "mentalhealth",
    "obsessivecompulsivedisorder",
    "olderadultmentalhealth",
    "panicdisorder",
    "phobias",
    "posttraumaticstressdisorder",
    "postpartumdepression",
    "seasonalaffectivedisorder",
    "stress",
    "teenmentalhealth",
)
NEVER = (
    "antidepressants",
    "suicide",
    "selfharm",
    "psychoticdisorders",
    "schizophrenia",
    "eatingdisorders",
    "personalitydisorders",
    "bipolardisorder",
    "dementia",
    "compulsivegambling",
    "dualdiagnosis",
)
GROUP_PAGE = (
    "<html><body><main>"
    + "".join(f'<a href="/{slug}.html">{slug}</a>' for slug in REVIEWED + NEVER)
    + '<a href="/xml.html">XML</a><a href="https://www.nimh.nih.gov/health/topics">NIMH</a>'
    + "</main></body></html>"
)
NARRATIVE = (
    "Stress — What is stress?: Stress is how your brain and body respond to a challenge or demand. Everyone feels "
    "stress from time to time. Simple things like regular activity, good sleep and talking with people you trust can "
    "help you cope with stress and protect your mental health."
)


def _row():
    return copy.deepcopy(manifest_row_for_key("medlineplus_consumer_health"))


def _robots():
    parser = robotparser.RobotFileParser()
    parser.parse(["User-agent: *", "Disallow: /xml/", "Disallow: /groupfeeds/", "Disallow: /feeds/topics/"])
    return parser


def test_medlineplus_is_authorised_for_d23_and_declares_only_the_group_hub():
    assert "D23" in specialized_allowed_entities_for_source("medlineplus_consumer_health")
    cfg = ld.discovery_config(_row())
    assert cfg is not None and cfg.hub_urls == (HUB,)
    assert str(_row()["governed_low_risk_eligibility"]).upper() in {"NO", "FALSE"}  # YAML reads NO as False


@pytest.mark.parametrize("slug", REVIEWED)
def test_every_reviewed_topic_is_in_the_d23_lane(slug):
    spec = resolve_specialized_entity_from_url(f"{MP}{slug}.html")
    assert spec is not None and spec.entity_id == "D23"


@pytest.mark.parametrize("slug", NEVER)
def test_crisis_medication_and_clinical_topics_are_never_admitted(slug):
    ok, reason, _ = ld.admit_discovered_url(
        f"{MP}{slug}.html", _row(), allowed_entities=specialized_allowed_entities_for_source("medlineplus_consumer_health")
    )
    assert not ok and reason in {"CONTENT_DENY", "NO_SAFETY_LANE"}


@pytest.mark.parametrize("url", [MP + "diabetes.html", MP + "multiplesclerosis.html", MP + "teendepression.html"])
def test_other_medlineplus_pages_keep_their_lane(url):
    spec = resolve_specialized_entity_from_url(url)
    assert spec is None or spec.entity_id != "D23"


def test_the_group_page_feed_admits_exactly_the_reviewed_topics():
    def fetch(url, domain):
        assert url == HUB
        return 200, "text/html", GROUP_PAGE.encode(), url

    result = ld.discover_for_row(
        _row(), known_keys=set(), budget=50, fetch_page=fetch, load_robots=lambda host: _robots()
    )
    assert sorted(a["url"] for a in result.admitted) == sorted(f"{MP}{s}.html" for s in REVIEWED)
    assert {a["entity_id"] for a in result.admitted} == {"D23"}
    assert result.rejected["DOMAIN_NOT_ALLOWED"] == 1


def test_narrative_education_passes_on_a_new_medlineplus_page():
    url = MP + "stress.html"
    ok, reason = content_quality_pass(NARRATIVE, resolve_specialized_entity_from_url(url), canonical_url=url)
    assert ok, reason


@pytest.mark.parametrize(
    "statement, reason",
    [
        (
            "Stress — Living With: Feeling Stressed? Ways to Improve Your Well-Being (National Institutes of Health) "
            "Also in Spanish Live Your Life Well (Mental Health America) stress anxiety",
            "MH_EDU_RESOURCE_LIST_BLOCK",
        ),
        (
            "Depression — Women: Depression (Department of Health and Human Services, Office on Women's Health) "
            "Depression and Aging (Centers for Disease Control and Prevention) depression mental health",
            "MH_EDU_RESOURCE_LIST_BLOCK",
        ),
        (
            "Depression — What are the treatments for depression?: Most treatments include medicines and talk "
            "therapy. Depression can get better and your mental health can improve with the right support.",
            "MH_EDU_MEDICATION_BLOCK",
        ),
        (
            "Anxiety — Getting help: If anxiety feels overwhelming you can call or text 988 at any time to talk with "
            "someone. Support from people you trust can also ease worry and stress.",
            "MH_EDU_US_CRISIS_ROUTE_BLOCK",
        ),
    ],
)
def test_new_medlineplus_pages_fail_closed_on_lists_medicines_and_us_crisis_routes(statement, reason):
    url = MP + ("stress.html" if statement.startswith("Stress") else "depression.html")
    spec = resolve_specialized_entity_from_url(url)
    assert _d23_mh_edu_content_blocked(statement, spec, canonical_url=url) == (True, reason)


def test_pages_eligible_before_r044_are_not_re_judged_by_the_new_rules():
    url = "https://www.nhs.uk/mental-health/conditions/generalised-anxiety-disorder-gad/"
    spec = resolve_specialized_entity_from_url(url)
    text = "Generalised anxiety disorder — Treatment: Talking therapies and medicines can both help people with anxiety."
    assert _d23_mh_edu_content_blocked(text, spec, canonical_url=url) == (False, "")
