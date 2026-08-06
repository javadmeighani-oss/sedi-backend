"""I5-IMPL-W2-P02 — full knowledge-unit runtime eligibility matrix (no DB).

Fail-closed. The W1-P02 provenance-only `evaluate_runtime_eligibility` remains
unchanged; static/runtime W2-P02 tests use this gate.
"""
from __future__ import annotations

from typing import Any, Mapping, Union

from backend.app.services.i5.enums import (
    ConflictState,
    EvidenceStrength,
    FreshnessState,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
)

_ELIGIBLE_EVIDENCE = frozenset(
    {
        EvidenceStrength.LOW.value,
        EvidenceStrength.MODERATE.value,
        EvidenceStrength.HIGH.value,
    }
)
_OK_CONFLICT = frozenset({ConflictState.NONE.value, ConflictState.RESOLVED.value})
_REVIEW_CONFLICT = frozenset(
    {ConflictState.SUSPECTED.value, ConflictState.CONFIRMED.value}
)
_BLOCKING_SAFETY = frozenset(
    {MedicalSafetyState.BLOCKED.value, MedicalSafetyState.RESTRICTED.value}
)
_BLOCKING_PUBLICATION = frozenset(
    {PublicationState.WITHDRAWN.value, PublicationState.SUPERSEDED.value}
)


def _as_mapping(ku: Union[Mapping[str, Any], Any]) -> Mapping[str, Any]:
    if isinstance(ku, Mapping):
        return ku
    keys = (
        "provenance_complete",
        "evidence_strength",
        "freshness_state",
        "conflict_state",
        "medical_safety_state",
        "publication_state",
        "retraction_reason",
        "runtime_eligibility",
    )
    return {key: getattr(ku, key, None) for key in keys}


def _norm_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def evaluate_knowledge_unit_eligibility(
    ku: Union[Mapping[str, Any], Any],
) -> KnowledgeUnitRuntimeEligibility:
    """Frozen fail-closed eligibility matrix for W2-P02."""
    data = _as_mapping(ku)

    retraction = _norm_str(data.get("retraction_reason"))
    if retraction:
        return KnowledgeUnitRuntimeEligibility.REVOKED

    medical = _norm_str(data.get("medical_safety_state")) or MedicalSafetyState.UNKNOWN.value
    publication = _norm_str(data.get("publication_state"))
    conflict = _norm_str(data.get("conflict_state")) or ConflictState.NONE.value

    if medical in _BLOCKING_SAFETY or publication == PublicationState.WITHDRAWN.value:
        return KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE

    if medical == MedicalSafetyState.PENDING_REVIEW.value or conflict in _REVIEW_CONFLICT:
        return KnowledgeUnitRuntimeEligibility.REVIEW_REQUIRED

    provenance_complete = bool(data.get("provenance_complete"))
    evidence = _norm_str(data.get("evidence_strength"))
    freshness = _norm_str(data.get("freshness_state"))

    eligible = (
        provenance_complete
        and evidence in _ELIGIBLE_EVIDENCE
        and freshness == FreshnessState.CURRENT.value
        and conflict in _OK_CONFLICT
        and medical == MedicalSafetyState.CLEARED.value
        and publication not in _BLOCKING_PUBLICATION
        and not retraction
    )
    if eligible:
        return KnowledgeUnitRuntimeEligibility.ELIGIBLE
    return KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
