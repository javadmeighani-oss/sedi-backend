"""R-044 open-licence library, nutrition / exercise / lifestyle: two public-domain sources on the low-risk path.

medlineplus_wellness (NIH / NLM MedlinePlus topic summaries) and odphp_health_gov (US HHS Physical Activity Guidelines,
Dietary Guidelines, Move Your Way). Both are US federal works (public domain). The low-risk path has no crisis or
medication phrase check, so the clinical topics are simply not in the source, and MedlinePlus lists of outside resources
are rejected by a manifest-switched guard that touches no other source.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
    ReviewState,
)
from backend.app.services.i5.governed_low_risk_eligibility import (
    domain_is_recognized_low_risk,
    finalize_governed_runtime_eligibility,
)
from backend.app.services.i5.governed_specialized_entity_eligibility import resolve_specialized_entity_from_url
from backend.app.services.i5.multisource_activation import _governance_evidence
from backend.app.services.i5.trusted_source_manifest import governed_low_risk_eligible, manifest_row_for_key
from backend.app.services.i5.wave02_coverage_identity import resolve_wave02_coverage_from_url

MP = "medlineplus_wellness"
OD = "odphp_health_gov"
NEVER_SLUGS = (
    "cholesterolmedicines", "eatingdisorders", "dietarysupplements", "herbalmedicine", "alcohol", "nutritionalsupport",
    "malabsorptionsyndromes", "obesity", "diabeticdiet", "suicide", "antidepressants", "sexualhealth",
)


def _urls(key):
    row = manifest_row_for_key(key)
    return [row["exact_url"], *row["additional_urls"]]


def _ku(statement, **over):
    base = dict(
        provenance_complete=True,
        evidence_strength=EvidenceStrength.UNKNOWN.value,
        medical_safety_state=MedicalSafetyState.PENDING_REVIEW.value,
        conflict_state=ConflictState.NONE.value,
        freshness_state=FreshnessState.UNKNOWN.value,
        review_state=ReviewState.NOT_REVIEWED.value,
        publication_state=PublicationState.DRAFT.value,
        runtime_eligibility=KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE.value,
        retraction_reason=None,
        domain="nutrition",
        topic_taxonomy="healthy_eating",
        normalized_statement=statement,
        manifest_entity_id=None,
        disease_or_health_condition=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("key, count", [(MP, 37), (OD, 13)])
def test_sources_are_public_domain_low_risk_with_attribution(key, count):
    row = manifest_row_for_key(key)
    assert row["activation"] in (True, "YES") and row["rights_terms_state"] == "PUBLIC_DOMAIN"
    assert row["robots_access_state"] == "ALLOWED" and governed_low_risk_eligible(key) is True
    assert "public" in row["license_notes"].lower() and "attribution" in row["license_notes"].lower()
    assert len(_urls(key)) == len(set(_urls(key))) == count
    assert f"max_{count}_urls" in row["rate_limit"]
    evidence = _governance_evidence(row)
    assert evidence["jurisdiction_country_code"] == "US" and evidence["authority_evidence_tier"] == "official_national"
    assert len(evidence["specialty_domain"]) <= 128 and len(evidence["permitted_use_restriction"]) <= 240


@pytest.mark.parametrize("key", [MP, OD])
def test_every_page_is_in_the_patterns_has_a_low_risk_domain_and_no_specialized_lane(key):
    patterns = [re.compile(p) for p in manifest_row_for_key(key)["allowed_url_patterns"]]
    for url in _urls(key):
        assert any(p.match(url) for p in patterns), url
        cov = resolve_wave02_coverage_from_url(url)
        assert cov is not None and domain_is_recognized_low_risk(cov.domain), url
        assert cov.domain in {"nutrition", "physical_activity_exercise", "lifestyle_prevention_routines"}, url
        assert resolve_specialized_entity_from_url(url) is None, url


def test_clinical_topics_are_not_in_the_library():
    urls = " ".join(_urls(MP) + _urls(OD))
    for slug in NEVER_SLUGS:
        assert f"/{slug}.html" not in urls, slug


def test_pages_that_already_belong_to_other_sources_are_not_duplicated():
    other = {u for k in ("medlineplus_consumer_health", "nhs_uk_live_well", "cdc_health_lifestyle") for u in _urls(k)}
    assert not (other & set(_urls(MP) + _urls(OD)))


def test_good_narrative_becomes_eligible_through_the_low_risk_path():
    url = "https://medlineplus.gov/vitamind.html"
    ku = _ku("Vitamin D — What is vitamin D?: Vitamin D helps your body absorb calcium and keeps bones strong. Sun, some foods and supplements are sources.")
    out = finalize_governed_runtime_eligibility(ku, source_key=MP, domain="nutrition", canonical_url=url)
    assert out == KnowledgeUnitRuntimeEligibility.ELIGIBLE and ku.review_state == ReviewState.APPROVED.value


RESOURCE_LIST = (
    "Vitamin D — Living With: Vitamin D: Fact Sheet for Consumers (National Institutes of Health) Also in Spanish "
    "Vitamin D and Your Bones (Mayo Foundation for Medical Education and Research)"
)


def test_a_list_of_outside_resources_is_never_made_eligible():
    url = "https://medlineplus.gov/vitamind.html"
    ku = _ku(RESOURCE_LIST)
    out = finalize_governed_runtime_eligibility(ku, source_key=MP, domain="nutrition", canonical_url=url)
    assert out != KnowledgeUnitRuntimeEligibility.ELIGIBLE and ku.publication_state == PublicationState.DRAFT.value


@pytest.mark.parametrize("key", [MP, OD])
def test_passages_about_medicines_are_not_made_eligible(key):
    ku = _ku("Caffeine — Who should avoid caffeine?: Check with your provider if you take certain medicines; some medicines interact with caffeine and may change how it affects you.")
    out = finalize_governed_runtime_eligibility(ku, source_key=key, domain="nutrition", canonical_url=_urls(key)[0])
    assert out != KnowledgeUnitRuntimeEligibility.ELIGIBLE and ku.review_state == ReviewState.NOT_REVIEWED.value


def test_the_resource_guard_touches_no_other_source():
    ku = _ku(RESOURCE_LIST)
    finalize_governed_runtime_eligibility(
        ku, source_key="nhs_uk_live_well", domain="nutrition", canonical_url="https://www.nhs.uk/live-well/eat-well/5-a-day/"
    )
    assert ku.review_state == ReviewState.APPROVED.value  # historical behaviour of every other low-risk source
    assert manifest_row_for_key("nhs_uk_live_well").get("reject_resource_lists") is None
    assert manifest_row_for_key("nhs_uk_live_well").get("reject_medicine_talk") is None
