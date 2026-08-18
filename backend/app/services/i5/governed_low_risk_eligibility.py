"""Deterministic governed low-risk KU eligibility (manifest-governed, fail-closed).

Only manifest entries with ``governed_low_risk_eligibility: YES`` may receive
automatic ELIGIBLE classification. High-risk domains, scientific literature
connectors, and PubMed paths remain REVIEW_REQUIRED / NOT_ELIGIBLE.
"""

from __future__ import annotations

from typing import Any, Optional, Union

from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
    ReviewState,
)
from backend.app.services.i5.medical_safety_gate import (
    assert_allowed_medical_safety_transition,
    domain_is_high_risk,
)
from backend.app.services.i5.runtime_eligibility_gate import evaluate_knowledge_unit_eligibility
from backend.app.services.i5.trusted_source_manifest import (
    governed_low_risk_eligible,
    manifest_row_for_key,
)

_HIGH_RISK_CONNECTOR_PREFIXES = (
    "pubmed",
    "clinicaltrials",
    "who_guideline",
    "catalog12",
    "know01:",
)


def connector_blocks_governed_low_risk(connector_or_source_key: Optional[str]) -> bool:
    if not connector_or_source_key:
        return True
    key = str(connector_or_source_key).casefold()
    return any(key.startswith(p) for p in _HIGH_RISK_CONNECTOR_PREFIXES)


def can_apply_governed_low_risk(
    *,
    source_key: str,
    domain: str,
    connector_key: Optional[str] = None,
    provenance_complete: bool,
) -> bool:
    if not provenance_complete:
        return False
    if connector_blocks_governed_low_risk(connector_key or source_key):
        return False
    if not governed_low_risk_eligible(source_key):
        return False
    if domain_is_high_risk(domain):
        return False
    return True


def apply_governed_low_risk_fields(
    ku: Any,
    *,
    source_key: str,
    domain: str,
) -> bool:
    """Mutate KU governance fields for manifest low-risk path. Returns True if applied."""
    if not can_apply_governed_low_risk(
        source_key=source_key,
        domain=domain,
        provenance_complete=bool(getattr(ku, "provenance_complete", False)),
    ):
        return False

    row = manifest_row_for_key(source_key) or {}
    evidence = str(row.get("eligibility_evidence_strength") or EvidenceStrength.LOW.value).upper()
    if evidence not in {e.value for e in EvidenceStrength if e != EvidenceStrength.UNKNOWN}:
        evidence = EvidenceStrength.LOW.value

    prior_medical = getattr(ku, "medical_safety_state", None) or MedicalSafetyState.UNKNOWN.value
    assert_allowed_medical_safety_transition(prior_medical, MedicalSafetyState.CLEARED)

    ku.evidence_strength = evidence
    ku.freshness_state = FreshnessState.CURRENT.value
    ku.medical_safety_state = MedicalSafetyState.CLEARED.value
    ku.conflict_state = ConflictState.NONE.value
    ku.review_state = ReviewState.APPROVED.value
    ku.publication_state = PublicationState.PUBLISHED.value
    return True


def finalize_governed_runtime_eligibility(
    ku: Union[Any, dict],
    *,
    source_key: str,
    domain: str,
    connector_key: Optional[str] = None,
) -> KnowledgeUnitRuntimeEligibility:
    if isinstance(ku, dict):
        prov_complete = bool(ku.get("provenance_complete"))
    else:
        prov_complete = bool(getattr(ku, "provenance_complete", False))

    if can_apply_governed_low_risk(
        source_key=source_key,
        domain=domain,
        connector_key=connector_key,
        provenance_complete=prov_complete,
    ):
        if not isinstance(ku, dict):
            apply_governed_low_risk_fields(ku, source_key=source_key, domain=domain)
    return evaluate_knowledge_unit_eligibility(ku)
