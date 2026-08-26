"""Hard exclusion decisions for KNOW-07 publication/retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union

from backend.app.services.i5.enums import (
    FreshnessState,
    KnowledgeUnitRuntimeEligibility,
    MedicalSafetyState,
    PublicationState,
)
from backend.app.services.i5.runtime_eligibility_gate import evaluate_knowledge_unit_eligibility


@dataclass(frozen=True)
class ExclusionDecision:
    excluded: bool
    reason: str
    code: str


def _as_map(ku: Union[Mapping[str, Any], Any]) -> Mapping[str, Any]:
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
        "supersession_state",
    )
    return {k: getattr(ku, k, None) for k in keys}


def hard_exclude_ku(
    ku: Union[Mapping[str, Any], Any],
    *,
    retracted_at: Any = None,
) -> ExclusionDecision:
    """Fail-closed hard exclusions — must block all retrieval branches."""
    data = _as_map(ku)

    if retracted_at is not None:
        return ExclusionDecision(True, "kce_retracted_at_set", "RETRACTED")

    retraction = str(data.get("retraction_reason") or "").strip()
    if retraction:
        return ExclusionDecision(True, "ku_retraction_reason", "RETRACTED")

    if not bool(data.get("provenance_complete")):
        return ExclusionDecision(True, "missing_required_provenance", "MISSING_PROVENANCE")

    pub = str(data.get("publication_state") or "").strip()
    if pub == PublicationState.SUPERSEDED.value:
        return ExclusionDecision(True, "publication_superseded", "SUPERSEDED")
    if pub == PublicationState.WITHDRAWN.value:
        return ExclusionDecision(True, "publication_withdrawn", "UNSAFE_BLOCKED")

    freshness = str(data.get("freshness_state") or "").strip()
    if freshness in {FreshnessState.STALE.value, FreshnessState.EXPIRED.value}:
        return ExclusionDecision(True, f"freshness_{freshness}", "STALE")

    safety = str(data.get("medical_safety_state") or "").strip()
    if safety in {MedicalSafetyState.BLOCKED.value, MedicalSafetyState.RESTRICTED.value}:
        return ExclusionDecision(True, f"safety_{safety}", "UNSAFE_BLOCKED")

    gate = evaluate_knowledge_unit_eligibility(data)
    if gate != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
        return ExclusionDecision(True, f"gate_{gate.value}", "INELIGIBLE")

    col = str(data.get("runtime_eligibility") or "").strip()
    if col and col != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
        return ExclusionDecision(True, "column_not_eligible", "INELIGIBLE")

    return ExclusionDecision(False, "ok", "ALLOW")


def assert_cannot_reenter(
    *,
    branch: str,
    exclusion: ExclusionDecision,
) -> None:
    """Any retrieval branch (lexical/vector/hybrid/fallback) must honor exclusion."""
    if not exclusion.excluded:
        return
    raise ValueError(f"EXCLUSION_REENTRY_FORBIDDEN:{branch}:{exclusion.code}")
