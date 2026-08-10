"""Runtime eligibility enforcement for SCIS retrieval candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.runtime_eligibility_gate import evaluate_knowledge_unit_eligibility


@dataclass
class EligibilityDecision:
    allowed: bool
    reason: str
    runtime_eligibility: Optional[str]


def is_kce_row_eligible(
    *,
    retracted_at: Any,
    runtime_eligibility_snapshot: Optional[str],
    ku: Any = None,
    expected_embedding_model: Optional[str] = None,
    row_model_identifier: Optional[str] = None,
    embedding_status: Optional[str] = None,
    backend_kind: Optional[str] = None,
) -> EligibilityDecision:
    if retracted_at is not None:
        return EligibilityDecision(False, "retracted", "REVOKED")
    if embedding_status and embedding_status != "ready":
        return EligibilityDecision(False, "embedding_not_ready", runtime_eligibility_snapshot)
    if expected_embedding_model and row_model_identifier and row_model_identifier != expected_embedding_model:
        return EligibilityDecision(False, "embedding_model_mismatch", runtime_eligibility_snapshot)
    if ku is not None:
        gate = evaluate_knowledge_unit_eligibility(ku)
        if gate != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
            return EligibilityDecision(False, f"ku_gate_{gate.value}", gate.value)
        # DB column must agree when present
        ku_el = getattr(ku, "runtime_eligibility", None)
        if ku_el and ku_el != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
            return EligibilityDecision(False, "ku_column_not_eligible", ku_el)
    elif runtime_eligibility_snapshot and runtime_eligibility_snapshot != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
        return EligibilityDecision(False, "snapshot_not_eligible", runtime_eligibility_snapshot)
    return EligibilityDecision(True, "ok", KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
