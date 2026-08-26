"""Specialized D18/D19 serving eligibility — MedlinePlus global low-risk stays NO."""
from __future__ import annotations

from types import SimpleNamespace

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
    can_apply_governed_low_risk,
    finalize_governed_runtime_eligibility,
)
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    SPECIALIZED_SOURCE_KEY,
    can_apply_specialized_entity_eligibility,
    content_quality_pass,
    resolve_specialized_entity_from_url,
    specialized_source_authorized,
    statement_dominated_by_nav_chrome,
    strip_html_nav_chrome,
)
from backend.app.services.i5.trusted_source_manifest import governed_low_risk_eligible


def _ku(**overrides):
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
        domain="lifestyle",
        topic_taxonomy="sleep",
        normalized_statement="placeholder",
        manifest_entity_id=None,
        disease_or_health_condition=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_medlineplus_global_low_risk_remains_no():
    assert governed_low_risk_eligible(SPECIALIZED_SOURCE_KEY) is False
    assert specialized_source_authorized(SPECIALIZED_SOURCE_KEY) is True
    assert can_apply_governed_low_risk(
        source_key=SPECIALIZED_SOURCE_KEY,
        domain="lifestyle",
        provenance_complete=True,
    ) is False


def test_url_resolves_d18_d19():
    assert resolve_specialized_entity_from_url(
        "https://medlineplus.gov/amyotrophiclateralsclerosis.html"
    ).entity_id == "D18"
    assert resolve_specialized_entity_from_url(
        "https://medlineplus.gov/multiplesclerosis.html"
    ).entity_id == "D19"
    assert resolve_specialized_entity_from_url("https://medlineplus.gov/diabetes.html") is None


def test_nav_chrome_rejection():
    chrome = (
        "skip to main content search the nhs website browse more home "
        "an official website of the united states government here's how you know"
    )
    assert statement_dominated_by_nav_chrome(chrome) is True
    ok, reason = content_quality_pass(chrome, resolve_specialized_entity_from_url(
        "https://medlineplus.gov/amyotrophiclateralsclerosis.html"
    ))
    assert ok is False
    assert reason == "NAV_CHROME_DOMINATED"


def test_specialized_d18_eligibility_pass():
    statement = (
        "Amyotrophic lateral sclerosis (ALS) is a nervous system disease that "
        "weakens muscles and impacts physical function. MedlinePlus consumer "
        "education summarizes symptoms and care topics for ALS."
    )
    ku = _ku(
        normalized_statement=statement,
        manifest_entity_id="D18",
        disease_or_health_condition="amyotrophic lateral sclerosis",
        domain="neurology_als",
        topic_taxonomy="als",
    )
    allowed, reason, spec = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/amyotrophiclateralsclerosis.html",
    )
    assert allowed and reason == "OK" and spec.entity_id == "D18"
    elig = finalize_governed_runtime_eligibility(
        ku,
        source_key=SPECIALIZED_SOURCE_KEY,
        domain="neurology_als",
        canonical_url="https://medlineplus.gov/amyotrophiclateralsclerosis.html",
    )
    assert elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert ku.manifest_entity_id == "D18"
    assert ku.medical_safety_state == MedicalSafetyState.CLEARED.value


def test_specialized_d19_eligibility_pass():
    statement = (
        "Multiple sclerosis (MS) is a disease that affects the central nervous "
        "system. Relapsing forms and demyelination are discussed in MedlinePlus "
        "consumer health summaries."
    )
    ku = _ku(
        normalized_statement=statement,
        manifest_entity_id="D19",
        disease_or_health_condition="multiple sclerosis",
        domain="neurology_ms",
        topic_taxonomy="ms",
    )
    elig = finalize_governed_runtime_eligibility(
        ku,
        source_key=SPECIALIZED_SOURCE_KEY,
        domain="neurology_ms",
        canonical_url="https://medlineplus.gov/multiplesclerosis.html",
    )
    assert elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE


def test_heart_disease_url_not_specialized_eligible():
    statement = (
        "Heart diseases include coronary artery disease and other conditions "
        "affecting the heart. This is general MedlinePlus consumer information."
    )
    ku = _ku(normalized_statement=statement, domain="lifestyle")
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/heartdiseases.html",
    )
    assert allowed is False
    assert reason in {"URL_NOT_IN_ENTITY_SCOPE", "ENTITY_IDENTITY_MISSING", "MISSING_CLINICAL_IDENTITY"}


def test_strip_html_nav_chrome_keeps_clinical():
    raw = (
        "skip to main content official website of the united states government "
        "Amyotrophic lateral sclerosis ALS weakens muscles over time and may "
        "affect breathing and speech according to consumer health education."
    )
    cleaned = strip_html_nav_chrome(raw)
    assert "amyotrophic" in cleaned.casefold()
    assert "skip to main content" not in cleaned.casefold()
