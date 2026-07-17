"""Section 15-I5-A1-R1 — Expanded governance contract tests (focused fix regressions)."""

from __future__ import annotations

import ast
import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path

from typing import Optional

import pytest

from backend.app.services.governance.contracts import (
    ALLOWING_EVIDENCE_USE_DECISIONS,
    CONTRACT_VERSION,
    EXPANDED_CONTRACT_VERSION,
    AuthoritySeparationOutcome,
    AuthorityUseCase,
    CareScope,
    ClinicalDomain,
    ClinicalJurisdiction,
    ClinicalJurisdictionScope,
    ConditionIdentifier,
    ConditionTerminology,
    ContradictionStatus,
    DiseasePackIdentity,
    DiseaseSystem,
    EvidenceCriticality,
    EvidenceFacet,
    EvidenceUseAssessment,
    EvidenceUseDecision,
    ExternalTaxonomyMapping,
    FreshnessStatus,
    FreshnessUseDecision,
    GovernedAuthorityKind,
    KnowledgeDomain,
    KnowledgePackGovernanceState,
    KnowledgePolicyDecision,
    KnowledgeRequirement,
    LicenseStatus,
    LocalizedClinicalTerm,
    LongevityEvidenceScope,
    PolicyOutcome,
    PredictionReasonCode,
    PredictionUseBoundary,
    PredictionUseCase,
    PredictionUseDecision,
    PreventionScope,
    PROHIBITED_PREDICTION_USE_CASES,
    PublicationState,
    ReviewStatus,
    RevocationDecision,
    RollbackDecision,
    RollbackRequirement,
    RollbackTarget,
    TaxonomyMappingRelation,
    evaluate_authority_separation,
    evaluate_freshness_criticality_use,
    evaluate_prediction_use,
    is_prohibited_prediction_use_case,
    jurisdiction_applies_to,
    jurisdictions_compatible,
    knowledge_policy_decision_permits_definitive_use,
    policy_outcome_equivalent_to_required_found,
)


def _global() -> ClinicalJurisdiction:
    return ClinicalJurisdiction(scope=ClinicalJurisdictionScope.GLOBAL)


def _country(code: str = "IR") -> ClinicalJurisdiction:
    return ClinicalJurisdiction(scope=ClinicalJurisdictionScope.COUNTRY, country_code=code)


def _subdivision(country: str = "IR", subdivision: str = "TEH") -> ClinicalJurisdiction:
    return ClinicalJurisdiction(
        scope=ClinicalJurisdictionScope.SUBDIVISION,
        country_code=country,
        subdivision_code=subdivision,
    )


def _organization(
    country: str = "IR",
    org_id: str = "org-1",
    subdivision: Optional[str] = "TEH",
) -> ClinicalJurisdiction:
    return ClinicalJurisdiction(
        scope=ClinicalJurisdictionScope.ORGANIZATION,
        country_code=country,
        subdivision_code=subdivision,
        organization_id=org_id,
    )


def _condition(**overrides) -> ConditionIdentifier:
    base = dict(
        taxonomy_authority="auth.example",
        namespace="conditions",
        code="COND-001",
        jurisdiction=_country(),
        taxonomy_version="2026.1",
    )
    base.update(overrides)
    return ConditionIdentifier(**base)


def _terminology() -> ConditionTerminology:
    return ConditionTerminology(
        terms=(
            LocalizedClinicalTerm(language_tag="en", text="Example condition", is_preferred=True),
            LocalizedClinicalTerm(language_tag="fa", text="مثال", is_preferred=True),
        ),
    )


def _pack_identity(**overrides) -> DiseasePackIdentity:
    base = dict(
        pack_id="pack-1",
        condition=_condition(),
        knowledge_domain=KnowledgeDomain.CLINICAL_DISEASE,
        clinical_domain=ClinicalDomain.CHRONIC,
        disease_system=DiseaseSystem.NERVOUS_SYSTEM,
        pack_version="1.0.0",
        jurisdiction=_country(),
        terminology=_terminology(),
    )
    base.update(overrides)
    return DiseasePackIdentity(**base)


def _knowledge_requirement(**overrides) -> KnowledgeRequirement:
    base = dict(
        knowledge_domain=KnowledgeDomain.CLINICAL_DISEASE,
        decision=KnowledgePolicyDecision.REQUIRED_FOUND,
        required_evidence_facets=(EvidenceFacet.DEFINITION,),
        jurisdiction=_country(),
        citation_required=True,
        reason_codes=("clinical_answer",),
        evidence_references=("evidence-1",),
    )
    base.update(overrides)
    return KnowledgeRequirement(**base)


def _pack_state(**overrides) -> KnowledgePackGovernanceState:
    base = dict(
        review_status=ReviewStatus.APPROVED,
        publication_state=PublicationState.PUBLISHED,
        freshness_status=FreshnessStatus.FRESH,
        license_status=LicenseStatus.EXPLICIT_GRANT,
        contradiction_status=ContradictionStatus.NONE,
        revocation_decision=RevocationDecision.NOT_REVOKED,
        authority_kind=GovernedAuthorityKind.CLINICAL_EVIDENCE,
        jurisdiction=_country(),
        evidence_criticality=EvidenceCriticality.CLINICAL,
        high_risk_change=False,
        rollback=None,
    )
    base.update(overrides)
    return KnowledgePackGovernanceState(**base)


def _evidence_allow(**overrides) -> EvidenceUseAssessment:
    base = dict(
        decision=EvidenceUseDecision.ALLOW_WITH_CITATION,
        pack_state=_pack_state(),
        pack_identity=_pack_identity(),
        requested_use=AuthorityUseCase.CLINICAL_ANSWER,
        requested_jurisdiction=_country(),
        knowledge_requirement=_knowledge_requirement(),
        evidence_criticality=EvidenceCriticality.CLINICAL,
        evidence_facets=(EvidenceFacet.DEFINITION,),
        citation_required=True,
        reason_codes=("citation_ok",),
        evidence_references=("evidence-1",),
    )
    base.update(overrides)
    return EvidenceUseAssessment(**base)


def _prediction_boundary(**overrides) -> PredictionUseBoundary:
    base = dict(
        use_case=PredictionUseCase.RISK_FACTOR_IDENTIFICATION,
        has_authorized_user_data=True,
        has_provenance=True,
        has_user_consent=True,
        has_sufficient_data=True,
        has_i4_safety_clearance=True,
        has_governed_evidence=True,
        has_uncertainty_representation=True,
        jurisdiction_mismatch=False,
        freshness=FreshnessStatus.FRESH,
        reason_codes=(PredictionReasonCode.AUTHORIZED_USE,),
    )
    base.update(overrides)
    return PredictionUseBoundary(**base)


def _mapping(**overrides) -> ExternalTaxonomyMapping:
    base = dict(
        local_condition=_condition(),
        external_authority="ext.auth",
        external_namespace="ext.ns",
        external_code="EXT-1",
        taxonomy_version="1.0",
        jurisdiction=_country(),
        relation=TaxonomyMappingRelation.EXACT,
        mapping_evidence_refs=("map-ev-1",),
        license_status=LicenseStatus.EXPLICIT_GRANT,
        display_permitted=False,
        storage_permitted=True,
        translation_permitted=False,
        derivative_work_permitted=False,
        redistribution_permitted=False,
    )
    base.update(overrides)
    return ExternalTaxonomyMapping(**base)


# --- version / enum stability ---


def test_expanded_contract_version_stable():
    assert EXPANDED_CONTRACT_VERSION == "sedi.governance.expanded-contracts.v1"


def test_existing_contract_version_unchanged():
    assert CONTRACT_VERSION == "sedi.governance.contracts.v1"


def test_knowledge_domain_enum_values_stable():
    assert KnowledgeDomain.CLINICAL_DISEASE.value == "clinical_disease"


def test_evidence_facet_count_and_values_are_stable():
    assert len(EvidenceFacet) == 23
    assert EvidenceFacet.MEDICATION_SAFETY.value == "medication_safety"


def test_prevention_care_longevity_scope_values_stable():
    assert PreventionScope.PRIMARY_PREVENTION.value == "primary_prevention"
    assert CareScope.PALLIATIVE_SUPPORT.value == "palliative_support"
    assert LongevityEvidenceScope.HEALTHY_AGEING.value == "healthy_ageing"


def test_disease_system_has_no_individual_disease_members():
    forbidden = {"als", "ms", "hepatitis", "heart_failure", "parkinson", "parkinson_disease"}
    assert {m.value for m in DiseaseSystem}.isdisjoint(forbidden)


def test_frozen_dataclasses():
    with pytest.raises(FrozenInstanceError):
        _country().country_code = "US"  # type: ignore[misc]


# --- F02 / Phase 4 directional jurisdiction ---


def test_different_organizations_same_country_incompatible():
    left = _organization(org_id="org-a", subdivision=None)
    right = _organization(org_id="org-b", subdivision=None)
    assert jurisdiction_applies_to(left, right) is False
    assert jurisdictions_compatible(left, right) is False


def test_different_organizations_same_subdivision_incompatible():
    left = _organization(org_id="org-a", subdivision="TEH")
    right = _organization(org_id="org-b", subdivision="TEH")
    assert jurisdiction_applies_to(left, right) is False


def test_organization_versus_country_directional():
    org = _organization()
    country = _country()
    assert jurisdiction_applies_to(country, org) is True
    assert jurisdiction_applies_to(org, country) is False


def test_global_source_to_country_request():
    assert jurisdiction_applies_to(_global(), _country()) is True


def test_country_source_to_global_request_fails():
    assert jurisdiction_applies_to(_country(), _global()) is False


def test_country_source_to_same_country_subdivision():
    assert jurisdiction_applies_to(_country("IR"), _subdivision("IR", "TEH")) is True


def test_subdivision_source_to_different_subdivision_fails():
    assert (
        jurisdiction_applies_to(_subdivision("IR", "TEH"), _subdivision("IR", "ISF"))
        is False
    )


def test_missing_organization_identifier_fails_closed():
    with pytest.raises(ValueError, match="organization_id_required"):
        ClinicalJurisdiction(
            scope=ClinicalJurisdictionScope.ORGANIZATION,
            country_code="IR",
            organization_id="",
        )


def test_mutual_compatibility_requires_both_directions():
    assert jurisdictions_compatible(_country("IR"), _country("IR")) is True
    assert jurisdictions_compatible(_global(), _country()) is False


# --- F06 / F07 taxonomy ---


def test_unverified_mapping_cannot_carry_any_use_right():
    with pytest.raises(ValueError, match="unverified_mapping_cannot_permit_any_use"):
        _mapping(
            relation=TaxonomyMappingRelation.UNVERIFIED,
            display_permitted=False,
            storage_permitted=False,
            translation_permitted=True,
            derivative_work_permitted=False,
            redistribution_permitted=False,
        )


def test_blocked_license_cannot_permit_use():
    with pytest.raises(ValueError, match="blocked_license_cannot_permit_use"):
        _mapping(license_status=LicenseStatus.UNKNOWN, display_permitted=True)


def test_restricted_mapping_cannot_carry_every_right():
    with pytest.raises(ValueError, match="restricted_license_cannot_permit_every_right"):
        _mapping(
            license_status=LicenseStatus.RESTRICTED,
            display_permitted=True,
            storage_permitted=True,
            translation_permitted=True,
            derivative_work_permitted=True,
            redistribution_permitted=True,
        )


def test_mapping_jurisdiction_must_fit_local_condition():
    with pytest.raises(ValueError, match="mapping_jurisdiction_outside_condition_applicability"):
        _mapping(
            local_condition=_condition(jurisdiction=_country("IR")),
            jurisdiction=_country("US"),
        )


def test_taxonomy_mapping_rejects_duplicate_evidence_refs():
    with pytest.raises(ValueError, match="mapping_evidence_refs_duplicate"):
        _mapping(mapping_evidence_refs=("map-ev-1", "map-ev-1"))


# --- terminology / pack identity ---


def test_terminology_requires_preferred_and_rejects_duplicates():
    with pytest.raises(ValueError, match="preferred_label_required"):
        ConditionTerminology(
            terms=(LocalizedClinicalTerm(language_tag="en", text="x", is_preferred=False),),
        )
    with pytest.raises(ValueError, match="duplicate_preferred_label"):
        ConditionTerminology(
            terms=(
                LocalizedClinicalTerm(language_tag="en", text="a", is_preferred=True),
                LocalizedClinicalTerm(language_tag="en", text="b", is_preferred=True),
            ),
        )


def test_disease_pack_allows_unknown_domain_for_storage():
    pack = _pack_identity(
        clinical_domain=ClinicalDomain.UNKNOWN,
        disease_system=DiseaseSystem.UNKNOWN,
    )
    assert pack.clinical_domain is ClinicalDomain.UNKNOWN


def test_disease_pack_rejects_jurisdiction_conflict():
    with pytest.raises(ValueError, match="condition_pack_jurisdiction_conflict"):
        _pack_identity(
            condition=_condition(jurisdiction=_country("US")),
            jurisdiction=_country("IR"),
        )


# --- knowledge policy ---


def test_required_found_requires_evidence_and_citation():
    with pytest.raises(ValueError, match="required_found_requires_evidence"):
        _knowledge_requirement(evidence_references=())
    with pytest.raises(ValueError, match="required_found_requires_citation"):
        _knowledge_requirement(citation_required=False)


def test_not_required_cannot_carry_evidence():
    with pytest.raises(ValueError, match="not_required_cannot_carry_evidence"):
        _knowledge_requirement(
            decision=KnowledgePolicyDecision.NOT_REQUIRED,
            evidence_references=("evidence-1",),
        )


def test_policy_outcome_allow_is_not_required_found():
    assert policy_outcome_equivalent_to_required_found(PolicyOutcome.ALLOW) is False
    assert knowledge_policy_decision_permits_definitive_use(
        KnowledgePolicyDecision.REQUIRED_INSUFFICIENT
    ) is False


# --- F03 / F08 pack prefilter ---


def test_pack_prefilter_passes_only_clean_published_state():
    assert _pack_state().passes_pack_state_prefilter() is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"review_status": ReviewStatus.QUARANTINED},
        {"review_status": ReviewStatus.PENDING_HUMAN},
        {"publication_state": PublicationState.UNPUBLISHED},
        {"publication_state": PublicationState.SUPERSEDED},
        {"publication_state": PublicationState.SUSPENDED},
        {"publication_state": PublicationState.WITHDRAWN},
        {"license_status": LicenseStatus.RESTRICTED},
        {"license_status": LicenseStatus.UNKNOWN},
        {"freshness_status": FreshnessStatus.SOFT_STALE},
        {"freshness_status": FreshnessStatus.HARD_STALE},
        {"freshness_status": FreshnessStatus.UNKNOWN_AGE},
        {"contradiction_status": ContradictionStatus.DETECTED_UNRESOLVED},
        {"contradiction_status": ContradictionStatus.ACCEPTED_DIVERGENCE},
        {"contradiction_status": ContradictionStatus.BLOCKED},
        {"revocation_decision": RevocationDecision.REVOKED},
        {"revocation_decision": RevocationDecision.SUSPENDED},
        {"revocation_decision": RevocationDecision.REVIEW_REQUIRED},
        {"high_risk_change": True},
        {"authority_kind": GovernedAuthorityKind.PROVIDER_IDENTITY},
        {
            "rollback": RollbackRequirement(
                decision=RollbackDecision.REQUIRED,
                source_artifact_identity="current-1",
                target=RollbackTarget(approved_baseline_identity="baseline-1"),
            )
        },
        {
            "rollback": RollbackRequirement(
                decision=RollbackDecision.BLOCKED_NO_APPROVED_BASELINE,
                source_artifact_identity="current-1",
                target=None,
            )
        },
    ],
)
def test_pack_prefilter_rejects_prohibited_lifecycle_states(overrides):
    assert _pack_state(**overrides).passes_pack_state_prefilter() is False


def test_pack_prefilter_is_not_final_answer_permission():
    doc = KnowledgePackGovernanceState.passes_pack_state_prefilter.__doc__ or ""
    assert "final answer permission" in doc
    assert "requested use case" in doc
    assert not hasattr(KnowledgePackGovernanceState, "eligible_for_unrestricted_use")


# --- F12 rollback ---


def test_rollback_target_cannot_equal_source():
    with pytest.raises(ValueError, match="rollback_target_cannot_equal_source"):
        RollbackRequirement(
            decision=RollbackDecision.REQUIRED,
            source_artifact_identity="same-id",
            target=RollbackTarget(approved_baseline_identity="same-id"),
        )


def test_blocked_rollback_cannot_carry_target():
    with pytest.raises(ValueError, match="blocked_rollback_cannot_carry_target"):
        RollbackRequirement(
            decision=RollbackDecision.BLOCKED_NO_APPROVED_BASELINE,
            source_artifact_identity="current-1",
            target=RollbackTarget(approved_baseline_identity="baseline-1"),
        )


def test_not_required_rollback_cannot_carry_target():
    with pytest.raises(ValueError, match="not_required_rollback_cannot_carry_target"):
        RollbackRequirement(
            decision=RollbackDecision.NOT_REQUIRED,
            source_artifact_identity="current-1",
            target=RollbackTarget(approved_baseline_identity="baseline-1"),
        )


def test_completed_rollback_requires_distinct_target():
    req = RollbackRequirement(
        decision=RollbackDecision.COMPLETED,
        source_artifact_identity="current-1",
        target=RollbackTarget(approved_baseline_identity="baseline-1"),
    )
    assert req.target.approved_baseline_identity == "baseline-1"


# --- F01 / F04 / F05 / F09 evidence lifecycle binding ---


def test_clean_allow_with_citation_constructs():
    assessment = _evidence_allow()
    assert assessment.decision is EvidenceUseDecision.ALLOW_WITH_CITATION


def test_evidence_allow_blocked_by_quarantine():
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(pack_state=_pack_state(review_status=ReviewStatus.QUARANTINED))
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(review_status=ReviewStatus.QUARANTINED),
        )


def test_pending_human_cannot_receive_restricted_allow():
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(review_status=ReviewStatus.PENDING_HUMAN),
        )


def test_high_risk_cannot_receive_restricted_allow():
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(high_risk_change=True),
        )


def test_evidence_allow_blocked_by_unpublished_state():
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(pack_state=_pack_state(publication_state=PublicationState.UNPUBLISHED))
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(publication_state=PublicationState.UNPUBLISHED),
        )


def test_evidence_allow_blocked_by_superseded_state():
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(pack_state=_pack_state(publication_state=PublicationState.SUPERSEDED))
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(publication_state=PublicationState.SUPERSEDED),
        )


def test_evidence_allow_blocked_by_restricted_license():
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(pack_state=_pack_state(license_status=LicenseStatus.RESTRICTED))
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(license_status=LicenseStatus.RESTRICTED),
        )


def test_evidence_allow_blocked_by_rollback_required():
    rollback = RollbackRequirement(
        decision=RollbackDecision.REQUIRED,
        source_artifact_identity="current-1",
        target=RollbackTarget(approved_baseline_identity="baseline-1"),
    )
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(pack_state=_pack_state(rollback=rollback))
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(rollback=rollback),
        )


def test_evidence_allow_blocked_by_authority_mismatch():
    with pytest.raises(ValueError, match="authority_use_mismatch"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(
                authority_kind=GovernedAuthorityKind.PROVIDER_IDENTITY,
            ),
            requested_use=AuthorityUseCase.CLINICAL_ANSWER,
        )


def test_evidence_allow_blocked_by_requested_jurisdiction_mismatch():
    with pytest.raises(ValueError, match="evidence_jurisdiction_mismatch"):
        _evidence_allow(requested_jurisdiction=_country("US"))


def test_evidence_allow_blocked_by_unknown_domain():
    with pytest.raises(ValueError, match="unknown_clinical_domain_cannot_allow"):
        _evidence_allow(
            pack_identity=_pack_identity(clinical_domain=ClinicalDomain.UNKNOWN),
        )


def test_evidence_allow_blocked_by_unknown_disease_system():
    with pytest.raises(ValueError, match="unknown_disease_system_cannot_allow"):
        _evidence_allow(
            pack_identity=_pack_identity(disease_system=DiseaseSystem.UNKNOWN),
        )


def test_unresolved_contradiction_blocks_all_allow():
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            pack_state=_pack_state(
                contradiction_status=ContradictionStatus.DETECTED_UNRESOLVED
            ),
        )
    with pytest.raises(ValueError, match="lifecycle_blocks_allowing_decision"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(
                contradiction_status=ContradictionStatus.DETECTED_UNRESOLVED,
                freshness_status=FreshnessStatus.SOFT_STALE,
            ),
            evidence_criticality=EvidenceCriticality.CLINICAL,
        )


def test_accepted_divergence_cannot_unrestricted_allow():
    with pytest.raises(ValueError, match="unrestricted_allow_requires_pack_prefilter"):
        _evidence_allow(
            pack_state=_pack_state(
                contradiction_status=ContradictionStatus.ACCEPTED_DIVERGENCE
            ),
        )


def test_accepted_divergence_may_allow_with_restrictions_when_lifecycle_ok():
    state = _pack_state(
        contradiction_status=ContradictionStatus.ACCEPTED_DIVERGENCE,
        freshness_status=FreshnessStatus.SOFT_STALE,
    )
    assert state.passes_pack_state_prefilter() is False
    assessment = _evidence_allow(
        decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
        pack_state=state,
        evidence_criticality=EvidenceCriticality.CLINICAL,
    )
    assert assessment.decision is EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS


def test_soft_stale_may_only_receive_restricted_allow():
    soft = _pack_state(freshness_status=FreshnessStatus.SOFT_STALE)
    with pytest.raises(ValueError, match="unrestricted_allow_requires_pack_prefilter"):
        _evidence_allow(
            pack_state=soft,
            evidence_criticality=EvidenceCriticality.CLINICAL,
        )
    assessment = _evidence_allow(
        decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
        pack_state=soft,
        evidence_criticality=EvidenceCriticality.CLINICAL,
    )
    assert assessment.decision is EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS


def test_safety_critical_soft_stale_cannot_unrestricted_allow():
    with pytest.raises(ValueError, match="unrestricted_allow_requires_pack_prefilter"):
        _evidence_allow(
            pack_state=_pack_state(freshness_status=FreshnessStatus.SOFT_STALE),
            evidence_criticality=EvidenceCriticality.SAFETY_CRITICAL,
        )


def test_safety_critical_hard_stale_blocks_restricted_allow():
    with pytest.raises(ValueError, match="freshness_blocks_allow"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(freshness_status=FreshnessStatus.HARD_STALE),
            evidence_criticality=EvidenceCriticality.SAFETY_CRITICAL,
        )


def test_safety_critical_unknown_age_blocks_restricted_allow():
    with pytest.raises(ValueError, match="freshness_blocks_allow"):
        _evidence_allow(
            decision=EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
            pack_state=_pack_state(freshness_status=FreshnessStatus.UNKNOWN_AGE),
            evidence_criticality=EvidenceCriticality.SAFETY_CRITICAL,
        )


def test_unrestricted_safe_state_receives_allow_with_citation():
    assessment = _evidence_allow()
    assert assessment.decision is EvidenceUseDecision.ALLOW_WITH_CITATION
    assert assessment.pack_state.passes_pack_state_prefilter() is True


def test_restricted_soft_stale_state_cannot_receive_unrestricted_allow():
    with pytest.raises(ValueError, match="unrestricted_allow_requires_pack_prefilter"):
        _evidence_allow(
            pack_state=_pack_state(
                freshness_status=FreshnessStatus.SOFT_STALE,
                contradiction_status=ContradictionStatus.ACCEPTED_DIVERGENCE,
            ),
            evidence_criticality=EvidenceCriticality.CLINICAL,
        )


def test_required_evidence_facets_must_be_present():
    with pytest.raises(ValueError, match="required_evidence_facets_missing"):
        _evidence_allow(evidence_facets=(EvidenceFacet.PREVENTION,))


def test_knowledge_requirement_must_be_required_found():
    with pytest.raises(ValueError, match="allow_requires_required_found"):
        _evidence_allow(
            knowledge_requirement=_knowledge_requirement(
                decision=KnowledgePolicyDecision.REQUIRED_INSUFFICIENT,
                citation_required=True,
                evidence_references=("evidence-1",),
            )
        )


def test_deny_decision_still_requires_pack_binding_fields():
    assessment = _evidence_allow(
        decision=EvidenceUseDecision.DENY_QUARANTINED,
        pack_state=_pack_state(review_status=ReviewStatus.QUARANTINED),
        evidence_references=(),
        evidence_facets=(),
    )
    assert assessment.decision is EvidenceUseDecision.DENY_QUARANTINED


# --- authority matrix ---


def test_authority_separation_matrix_and_ranking_denied():
    assert (
        evaluate_authority_separation(
            GovernedAuthorityKind.CLINICAL_EVIDENCE,
            AuthorityUseCase.CLINICAL_ANSWER,
        )
        is AuthoritySeparationOutcome.PERMITTED
    )
    for authority in GovernedAuthorityKind:
        assert (
            evaluate_authority_separation(authority, AuthorityUseCase.PROVIDER_RANKING)
            is AuthoritySeparationOutcome.DENIED
        )


# --- freshness matrix samples ---


def test_freshness_criticality_matrix_samples():
    assert (
        evaluate_freshness_criticality_use(
            EvidenceCriticality.SAFETY_CRITICAL, FreshnessStatus.SOFT_STALE
        )
        is FreshnessUseDecision.RESTRICTED
    )
    assert (
        evaluate_freshness_criticality_use(
            EvidenceCriticality.SAFETY_CRITICAL, FreshnessStatus.HARD_STALE
        )
        is FreshnessUseDecision.DENIED
    )
    assert (
        evaluate_freshness_criticality_use(
            EvidenceCriticality.CLINICAL, FreshnessStatus.UNKNOWN_AGE
        )
        is FreshnessUseDecision.DENIED
    )


# --- F10 / F11 prediction ---


def test_insufficient_data_is_reason_not_use_case():
    assert not hasattr(PredictionUseCase, "INSUFFICIENT_DATA")
    assert PredictionReasonCode.INSUFFICIENT_DATA.value == "insufficient_data"
    names = {member.name for member in PredictionUseCase}
    assert "INSUFFICIENT_DATA" not in names


def test_insufficient_data_yields_require_more_data():
    assert (
        evaluate_prediction_use(_prediction_boundary(has_sufficient_data=False))
        is PredictionUseDecision.REQUIRE_MORE_DATA
    )
    assert (
        evaluate_prediction_use(
            _prediction_boundary(
                reason_codes=(
                    PredictionReasonCode.AUTHORIZED_USE,
                    PredictionReasonCode.INSUFFICIENT_DATA,
                )
            )
        )
        is PredictionUseDecision.REQUIRE_MORE_DATA
    )


def test_prediction_soft_stale_cannot_allow():
    assert (
        evaluate_prediction_use(_prediction_boundary(freshness=FreshnessStatus.SOFT_STALE))
        is PredictionUseDecision.REQUIRE_HUMAN_REVIEW
    )


@pytest.mark.parametrize("use_case", sorted(PROHIBITED_PREDICTION_USE_CASES, key=lambda x: x.value))
def test_prohibited_prediction_use_cases_are_blocked(use_case):
    assert is_prohibited_prediction_use_case(use_case) is True
    assert (
        evaluate_prediction_use(_prediction_boundary(use_case=use_case))
        is PredictionUseDecision.BLOCKED
    )


def test_prediction_allow_requires_all_preconditions():
    assert evaluate_prediction_use(_prediction_boundary()) is PredictionUseDecision.ALLOW


def test_prediction_missing_consent_and_uncertainty_never_allow():
    assert (
        evaluate_prediction_use(_prediction_boundary(has_user_consent=False))
        is PredictionUseDecision.REQUIRE_CONSENT
    )
    assert (
        evaluate_prediction_use(_prediction_boundary(has_uncertainty_representation=False))
        is PredictionUseDecision.REQUIRE_MORE_DATA
    )


def test_diagnosis_and_precise_lifetime_always_blocked():
    assert (
        evaluate_prediction_use(_prediction_boundary(use_case=PredictionUseCase.DIAGNOSIS))
        is PredictionUseDecision.BLOCKED
    )
    assert (
        evaluate_prediction_use(
            _prediction_boundary(use_case=PredictionUseCase.PRECISE_REMAINING_LIFETIME)
        )
        is PredictionUseDecision.BLOCKED
    )


# --- import hygiene ---


def test_contracts_module_uses_stdlib_only_imports():
    mod = __import__("backend.app.services.governance.contracts", fromlist=["contracts"])
    tree = ast.parse(inspect.getsource(mod))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots <= {
        "__future__",
        "dataclasses",
        "datetime",
        "enum",
        "re",
        "typing",
    }


def test_expanded_test_file_has_no_forbidden_imports():
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    forbidden_roots = {
        "fastapi",
        "pydantic",
        "sqlalchemy",
        "backend.app.models",
        "backend.app.routers",
        "backend.app.services.governance.policy_evaluator",
    }
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for name in imported:
        for forbidden in forbidden_roots:
            assert not name.startswith(forbidden)


def test_existing_review_status_values_unchanged():
    assert ReviewStatus.APPROVED.value == "approved"
    assert PublicationState.PUBLISHED.value == "published"
    assert ALLOWING_EVIDENCE_USE_DECISIONS == frozenset(
        {
            EvidenceUseDecision.ALLOW_WITH_CITATION,
            EvidenceUseDecision.ALLOW_WITH_RESTRICTIONS,
        }
    )
