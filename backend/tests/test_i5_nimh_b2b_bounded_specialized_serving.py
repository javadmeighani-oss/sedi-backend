"""SEDI-79 B2B: NIMH bounded educational specialized serving (D23 only)."""
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
    NIMH_SOURCE_KEY,
    SPECIALIZED_SOURCE_KEY,
    can_apply_specialized_entity_eligibility,
    content_quality_pass,
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
    statement_dominated_by_nav_chrome,
)
from backend.app.services.i5.trusted_source_manifest import (
    governed_low_risk_eligible,
    load_trusted_source_manifest,
    manifest_row_for_key,
)
from backend.app.services.intelligence import safety_risk


URL_SELF_CARE = "https://www.nimh.nih.gov/health/topics/caring-for-your-mental-health"
URL_STRESS = "https://www.nimh.nih.gov/health/publications/so-stressed-out-fact-sheet"
URL_ANXIETY = "https://www.nimh.nih.gov/health/topics/anxiety-disorders"
URL_DEPRESSION = "https://www.nimh.nih.gov/health/topics/depression"
URL_ARBITRARY = "https://www.nimh.nih.gov/health/publications/general-page"


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
        domain="mental_health_psychology",
        topic_taxonomy="mental_health_education",
        normalized_statement="placeholder",
        manifest_entity_id="D23",
        disease_or_health_condition="mental health education",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_nimh_low_risk_no_d23_only_specialized():
    load_trusted_source_manifest.cache_clear()
    assert governed_low_risk_eligible(NIMH_SOURCE_KEY) is False
    assert specialized_allowed_entities_for_source(NIMH_SOURCE_KEY) == {"D23"}
    assert can_apply_governed_low_risk(
        source_key=NIMH_SOURCE_KEY,
        domain="mental_health_psychology",
        provenance_complete=True,
    ) is False


def test_d23_url_resolution_needles_only():
    assert resolve_specialized_entity_from_url(URL_SELF_CARE).entity_id == "D23"
    assert resolve_specialized_entity_from_url(URL_STRESS).entity_id == "D23"
    assert resolve_specialized_entity_from_url(URL_ANXIETY).entity_id == "D23"
    assert resolve_specialized_entity_from_url(URL_DEPRESSION) is None
    assert resolve_specialized_entity_from_url(URL_ARBITRARY) is None


def test_self_care_educational_allowed():
    statement = (
        "Caring for your mental health includes recognizing stress, building routines, "
        "and using self-care strategies such as sleep, social connection, and relaxation. "
        "NIMH consumer education encourages reaching out for support when worry persists."
    )
    ku = _ku(normalized_statement=statement)
    allowed, reason, spec = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_SELF_CARE
    )
    assert allowed and reason == "OK" and spec.entity_id == "D23"
    elig = finalize_governed_runtime_eligibility(
        ku, source_key=NIMH_SOURCE_KEY, domain="mental_health_psychology", canonical_url=URL_SELF_CARE
    )
    assert elig == KnowledgeUnitRuntimeEligibility.ELIGIBLE
    assert ku.review_state == ReviewState.APPROVED.value


def test_stress_coping_educational_allowed():
    statement = (
        "Feeling stressed is common. Coping skills include deep breathing, physical activity, "
        "and taking breaks from overwhelming tasks. This NIMH fact sheet summarizes stress "
        "education for the public as general mental health self-care information."
    )
    ku = _ku(normalized_statement=statement, topic_taxonomy="stress")
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_STRESS
    )
    assert allowed and reason == "OK"


def test_anxiety_general_educational_allowed():
    statement = (
        "What is anxiety? Anxiety involves excessive fear or worry that can affect daily life. "
        "Signs may include restlessness and trouble concentrating. General coping includes "
        "relaxation and talking with trusted supports for mental health education."
    )
    ku = _ku(normalized_statement=statement, topic_taxonomy="anxiety")
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_ANXIETY
    )
    assert allowed and reason == "OK"


def test_anxiety_treatment_selection_blocked():
    statement = (
        "Anxiety disorders may be treated with psychotherapy and treatment selection should "
        "consider which medication fits the patient. Clinicians help choose a treatment plan "
        "for ongoing care and monitoring of symptoms over time."
    )
    ku = _ku(normalized_statement=statement, topic_taxonomy="anxiety")
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_ANXIETY
    )
    assert allowed is False
    assert reason in {"MH_EDU_BOUNDARY_BLOCK", "MH_EDU_ANXIETY_TREATMENT_BLOCK"}


def test_anxiety_medication_blocked():
    statement = (
        "General anxiety education notes that medication may be prescribed by a clinician "
        "when appropriate for some patients with persistent worry and related symptoms."
    )
    ku = _ku(normalized_statement=statement, topic_taxonomy="anxiety")
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_ANXIETY
    )
    assert allowed is False
    assert reason in {"MH_EDU_BOUNDARY_BLOCK", "MH_EDU_ANXIETY_TREATMENT_BLOCK", "DIAGNOSIS_PRESCRIPTION_EXPANSION"}


def test_crisis_self_harm_blocked():
    statement = (
        "If you are thinking about suicide or self-harm, call a crisis line immediately. "
        "This message is not general mental health education and must not be served as such."
    )
    ku = _ku(normalized_statement=statement)
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_SELF_CARE
    )
    assert allowed is False
    assert reason == "MH_EDU_BOUNDARY_BLOCK"


def test_depression_url_blocked():
    statement = (
        "Depression is a mood disorder that affects how you feel and function. This summary "
        "describes general mental health education themes without prescribing care paths."
    )
    ku = _ku(normalized_statement=statement, topic_taxonomy="depression")
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_DEPRESSION
    )
    assert allowed is False
    assert reason in {"ENTITY_IDENTITY_MISSING", "URL_NOT_IN_ENTITY_SCOPE", "ENTITY_NOT_AUTHORIZED_FOR_SOURCE"}


def test_arbitrary_nimh_health_url_blocked():
    statement = (
        "General mental health education encourages awareness of stress and self-care habits "
        "for wellbeing while seeking professional support when symptoms interfere with life."
    )
    ku = _ku(normalized_statement=statement)
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_ARBITRARY
    )
    assert allowed is False
    assert reason in {"ENTITY_IDENTITY_MISSING", "URL_NOT_IN_ENTITY_SCOPE"}


def test_research_nav_chrome_blocked():
    chrome = (
        "thinking about taking part in clinical research this page contains basic information "
        "about clinical research new website experience easier to find health information "
        "research funding opportunities at nimh"
    )
    ku = _ku(normalized_statement=chrome)
    assert statement_dominated_by_nav_chrome(chrome) is True
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_ANXIETY
    )
    assert allowed is False
    assert reason in {"NAV_CHROME_DOMINATED", "MISSING_CLINICAL_IDENTITY", "STATEMENT_TOO_SHORT"}


def test_d23_requires_nimh_source():
    statement = (
        "Caring for your mental health includes self-care, stress management, and relaxation "
        "techniques described in NIMH educational materials for the general public."
    )
    ku = _ku(normalized_statement=statement)
    allowed, reason, _ = can_apply_specialized_entity_eligibility(
        source_key=SPECIALIZED_SOURCE_KEY, ku=ku, canonical_url=URL_SELF_CARE
    )
    assert allowed is False
    assert reason == "ENTITY_NOT_AUTHORIZED_FOR_SOURCE"


def test_content_quality_pass_required():
    short = "Stress and coping."
    spec = resolve_specialized_entity_from_url(URL_STRESS)
    ok, reason = content_quality_pass(short, spec, canonical_url=URL_STRESS)
    assert ok is False
    ku = _ku(normalized_statement=short)
    allowed, reason2, _ = can_apply_specialized_entity_eligibility(
        source_key=NIMH_SOURCE_KEY, ku=ku, canonical_url=URL_STRESS
    )
    assert allowed is False
    assert reason2 == reason


def test_i4_safety_authority_preserved():
    templates = safety_risk.list_template_strings()
    assert any("crisis" in t.casefold() or "self_harm" in t for t in templates)


def test_medlineplus_b2a_regression_sample():
    load_trusted_source_manifest.cache_clear()
    mp = specialized_allowed_entities_for_source(SPECIALIZED_SOURCE_KEY)
    assert "D18" in mp and "D19" in mp and "D01" in mp and "D20" in mp
    assert "D23" not in mp
    row = manifest_row_for_key("nimh_nih_mental_health")
    assert "D23" in (row.get("specialized_serving_eligibility") or [])
