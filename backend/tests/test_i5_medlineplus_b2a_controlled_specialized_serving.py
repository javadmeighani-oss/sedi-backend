"""SEDI-79 B2A: MedlinePlus controlled specialized serving (D01–D11, D13–D16, D20–D22)."""
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
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.trusted_source_manifest import (
    governed_low_risk_eligible,
    load_trusted_source_manifest,
    manifest_row_for_key,
)


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
        domain="disease_clinical",
        topic_taxonomy="general",
        normalized_statement="placeholder",
        manifest_entity_id=None,
        disease_or_health_condition=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_medlineplus_global_low_risk_unchanged_no():
    load_trusted_source_manifest.cache_clear()
    assert governed_low_risk_eligible(SPECIALIZED_SOURCE_KEY) is False
    row = manifest_row_for_key(SPECIALIZED_SOURCE_KEY)
    assert row is not None
    low = str(row.get("governed_low_risk_eligibility") or "NO").strip().upper()
    assert low in {"NO", "FALSE", "0", ""}
    assert can_apply_governed_low_risk(
        source_key=SPECIALIZED_SOURCE_KEY,
        domain="disease_clinical",
        provenance_complete=True,
    ) is False
    # Specialized path must remain authorized while global low-risk stays off.
    assert specialized_allowed_entities_for_source(SPECIALIZED_SOURCE_KEY)


def test_medlineplus_specialized_allowlist_d01_d11_d13_d16_d18_d22():
    load_trusted_source_manifest.cache_clear()
    allowed = specialized_allowed_entities_for_source(SPECIALIZED_SOURCE_KEY)
    for eid in (
        "D01",
        "D02",
        "D03",
        "D04",
        "D05",
        "D06",
        "D07",
        "D08",
        "D09",
        "D10",
        "D11",
        "D13",
        "D14",
        "D15",
        "D16",
        "D18",
        "D19",
        "D20",
        "D21",
        "D22",
    ):
        assert eid in allowed
    assert "D12" not in allowed
    assert "D17" not in allowed


def test_clean_medlineplus_d01_specialized_clearable():
    statement = (
        "Cancer is a disease in which cells grow out of control. MedlinePlus "
        "consumer education summarizes oncology topics, treatment overview, and "
        "when to seek care without prescribing medication."
    )
    ku = _ku(
        normalized_statement=statement,
        manifest_entity_id="D01",
        disease_or_health_condition="oncology and supportive cancer care",
        domain="oncology",
        topic_taxonomy="cancer",
    )
    allowed, reason, spec = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/cancers.html",
    )
    assert allowed and reason == "OK" and spec.entity_id == "D01"
    elig = finalize_governed_runtime_eligibility(
        ku,
        source_key=SPECIALIZED_SOURCE_KEY,
        domain="oncology",
        canonical_url="https://medlineplus.gov/cancers.html",
    )
    assert elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert ku.medical_safety_state == MedicalSafetyState.CLEARED.value
    assert ku.review_state == ReviewState.APPROVED.value
    assert ku.publication_state == PublicationState.PUBLISHED.value


def test_wrong_entity_blocked():
    statement = (
        "Amyotrophic lateral sclerosis (ALS) is a nervous system disease that "
        "weakens muscles and impacts physical function over time for patients."
    )
    ku = _ku(
        normalized_statement=statement,
        manifest_entity_id="D18",
        disease_or_health_condition="amyotrophic lateral sclerosis",
        domain="neurology_als",
        topic_taxonomy="als",
    )
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/cancers.html",
    )
    assert allowed is False
    assert reason == "URL_NOT_IN_ENTITY_SCOPE"


def test_wrong_url_blocked_for_d01():
    statement = (
        "Cancer is a disease in which cells grow out of control. MedlinePlus "
        "consumer education summarizes oncology topics and supportive care."
    )
    ku = _ku(
        normalized_statement=statement,
        manifest_entity_id="D01",
        disease_or_health_condition="oncology and supportive cancer care",
        domain="oncology",
        topic_taxonomy="cancer",
    )
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/nutrition.html",
    )
    assert allowed is False
    assert reason == "URL_NOT_IN_ENTITY_SCOPE"


def test_nav_chrome_content_blocked():
    chrome = (
        "skip to main content search medlineplus about medlineplus "
        "an official website of the united states government here's how you know "
        "journal articles resources reference desk"
    )
    ku = _ku(normalized_statement=chrome, manifest_entity_id="D01")
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/cancers.html",
    )
    assert allowed is False
    assert reason in {"NAV_CHROME_DOMINATED", "MISSING_CLINICAL_IDENTITY", "STATEMENT_TOO_SHORT"}


def test_nutrition_approved_url_clean_claim_allowed():
    statement = (
        "Nutrition means getting the nutrients your body needs from food. "
        "MedlinePlus consumer health pages explain healthy eating, vitamins, "
        "and dietary patterns for everyday education without prescribing diets."
    )
    ku = _ku(
        normalized_statement=statement,
        manifest_entity_id="D20",
        disease_or_health_condition="nutrition",
        domain="nutrition",
        topic_taxonomy="nutrition",
    )
    allowed, reason, spec = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/nutrition.html",
    )
    assert allowed and reason == "OK" and spec.entity_id == "D20"
    elig = finalize_governed_runtime_eligibility(
        ku,
        source_key=SPECIALIZED_SOURCE_KEY,
        domain="nutrition",
        canonical_url="https://medlineplus.gov/nutrition.html",
    )
    assert elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE


def test_cardio_approved_url_clean_claim_allowed():
    statement = (
        "Heart diseases include coronary artery disease and other conditions "
        "affecting the cardiovascular system. MedlinePlus consumer education "
        "covers symptoms awareness and prevention topics without diagnosis."
    )
    ku = _ku(
        normalized_statement=statement,
        manifest_entity_id="D21",
        disease_or_health_condition="heart disease",
        domain="cardiovascular",
        topic_taxonomy="heart",
    )
    assert resolve_specialized_entity_from_url(
        "https://medlineplus.gov/heartdiseases.html"
    ).entity_id == "D21"
    allowed, reason, spec = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/heartdiseases.html",
    )
    assert allowed and reason == "OK" and spec.entity_id == "D21"


def test_diabetes_approved_url_clean_claim_allowed():
    statement = (
        "Diabetes is a disease that affects how the body uses blood glucose. "
        "MedlinePlus consumer health information summarizes insulin, symptoms, "
        "and care education topics without prescribing medication."
    )
    ku = _ku(
        normalized_statement=statement,
        manifest_entity_id="D22",
        disease_or_health_condition="diabetes",
        domain="diabetes_metabolic",
        topic_taxonomy="diabetes",
    )
    allowed, reason, spec = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/diabetes.html",
    )
    assert allowed and reason == "OK" and spec.entity_id == "D22"


def test_unscoped_disease_clinical_blocked():
    statement = (
        "This general disease clinical page discusses older adult health topics "
        "for consumer education including aging, prevention, and wellness care."
    )
    ku = _ku(
        normalized_statement=statement,
        domain="disease_clinical",
        topic_taxonomy="disease_clinical",
        manifest_entity_id=None,
    )
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/olderadulthealth.html",
    )
    assert allowed is False
    assert reason in {
        "ENTITY_IDENTITY_MISSING",
        "URL_NOT_IN_ENTITY_SCOPE",
        "ENTITY_NOT_AUTHORIZED_FOR_SOURCE",
        "MISSING_CLINICAL_IDENTITY",
    }


def test_d18_d19_regression_unchanged():
    als = (
        "Amyotrophic lateral sclerosis (ALS) is a nervous system disease that "
        "weakens muscles and impacts physical function. MedlinePlus consumer "
        "education summarizes symptoms and care topics for ALS."
    )
    ms = (
        "Multiple sclerosis (MS) is a disease that affects the central nervous "
        "system. Relapsing forms and demyelination are discussed in MedlinePlus "
        "consumer health summaries."
    )
    ku_als = _ku(
        normalized_statement=als,
        manifest_entity_id="D18",
        disease_or_health_condition="amyotrophic lateral sclerosis",
        domain="neurology_als",
        topic_taxonomy="als",
    )
    ku_ms = _ku(
        normalized_statement=ms,
        manifest_entity_id="D19",
        disease_or_health_condition="multiple sclerosis",
        domain="neurology_ms",
        topic_taxonomy="ms",
    )
    assert (
        finalize_governed_runtime_eligibility(
            ku_als,
            source_key=SPECIALIZED_SOURCE_KEY,
            domain="neurology_als",
            canonical_url="https://medlineplus.gov/amyotrophiclateralsclerosis.html",
        )
        == KnowledgeUnitRuntimeEligibility.ELIGIBLE
    )
    assert (
        finalize_governed_runtime_eligibility(
            ku_ms,
            source_key=SPECIALIZED_SOURCE_KEY,
            domain="neurology_ms",
            canonical_url="https://medlineplus.gov/multiplesclerosis.html",
        )
        == KnowledgeUnitRuntimeEligibility.ELIGIBLE
    )


def test_nimh_allowlist_untouched():
    load_trusted_source_manifest.cache_clear()
    row = manifest_row_for_key("nimh_nih_mental_health")
    assert row is not None
    assert str(row.get("governed_low_risk_eligibility") or "NO").upper() == "NO"
    specialized = {str(e).strip().upper() for e in (row.get("specialized_serving_eligibility") or [])}
    assert specialized == set()
    assert "D20" not in specialized
    assert "D21" not in specialized
    assert "D22" not in specialized


def test_no_eligibility_without_content_quality_pass():
    short = "Cancer cells grow."
    ku = _ku(
        normalized_statement=short,
        manifest_entity_id="D01",
        disease_or_health_condition="oncology and supportive cancer care",
        domain="oncology",
        topic_taxonomy="cancer",
    )
    ok_q, q_reason = content_quality_pass(short, resolve_specialized_entity_from_url(
        "https://medlineplus.gov/cancers.html"
    ))
    assert ok_q is False
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY,
        ku=ku,
        canonical_url="https://medlineplus.gov/cancers.html",
    )
    assert allowed is False
    assert reason == q_reason
