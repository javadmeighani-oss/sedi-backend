"""Phase2-A CASE_19/20 — retrieval-set contradiction + sufficiency fail-safe.

Reuses conflict_service.detect_structured_conflict (deterministic).
No LLM / free-text medical judgment. PERSONAL cannot overrule GOVERNED.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from backend.app.services.i5.conflict_service import detect_structured_conflict
from backend.app.services.i5.enums import ConflictState, EvidenceStrength

SUFFICIENCY_OK = "SUFFICIENT"
SUFFICIENCY_NO_ELIGIBLE = "NO_ELIGIBLE_ITEMS"
SUFFICIENCY_UNRESOLVED_CONFLICT = "UNRESOLVED_RETRIEVAL_SET_CONFLICT"
SUFFICIENCY_LOW_ONLY = "ALL_ELIGIBLE_EVIDENCE_STRENGTH_LOW"
SUFFICIENCY_PERSONAL_HISTORY_BLOCKED = "PERSONAL_HISTORY_NOT_GOVERNED"

_MODERATE_OR_HIGH = frozenset(
    {EvidenceStrength.MODERATE.value, EvidenceStrength.HIGH.value}
)
_LOW = EvidenceStrength.LOW.value
_UNRESOLVED = frozenset({ConflictState.SUSPECTED, ConflictState.CONFIRMED})


@dataclass(frozen=True)
class RetrievalSetConflictHit:
    left_canonical_unit_id: str
    right_canonical_unit_id: str
    left_immutable_version_id: str
    right_immutable_version_id: str
    conflict_state: str
    left_ku_id: Optional[int] = None
    right_ku_id: Optional[int] = None


@dataclass(frozen=True)
class SufficiencyDecision:
    sufficient: bool
    reason: str
    clarification_required: bool
    conflict_hits: tuple[RetrievalSetConflictHit, ...] = ()

    def to_audit_dict(self) -> dict:
        return {
            "sufficient": self.sufficient,
            "reason": self.reason,
            "clarification_required": self.clarification_required,
            "conflict_hits": [
                {
                    "left_canonical_unit_id": h.left_canonical_unit_id,
                    "right_canonical_unit_id": h.right_canonical_unit_id,
                    "left_immutable_version_id": h.left_immutable_version_id,
                    "right_immutable_version_id": h.right_immutable_version_id,
                    "conflict_state": h.conflict_state,
                    "left_ku_id": h.left_ku_id,
                    "right_ku_id": h.right_ku_id,
                }
                for h in self.conflict_hits
            ],
        }


def _item_conflict_proxy(item: Any) -> dict:
    """Map RetrievedKnowledgeItem → conflict_service compare shape."""
    return {
        "normalized_statement": getattr(item, "normalized_statement", None),
        "applicability": None,
        "exclusions": None,
        "medical_safety_state": getattr(item, "medical_safety_state", None),
        "evidence_strength": getattr(item, "evidence_strength", None),
        "domain": getattr(item, "domain", None),
        "topic_taxonomy": getattr(item, "topic_taxonomy", None),
        # Already eligibility-filtered on serving path.
        "provenance_complete": True,
    }


def detect_retrieval_set_contradictions(
    items: Sequence[Any],
) -> tuple[RetrievalSetConflictHit, ...]:
    """Pairwise structured conflict among eligible retrieval-set items.

    Reuses conflict_service.detect_structured_conflict. Retrieval-set fail-closed
    only when normalized_statement or medical_safety_state diverge on the same
    domain/topic. Evidence-strength-only differences are ranking signals, not
    unresolved contradictions for sufficiency.
    """
    hits: list[RetrievalSetConflictHit] = []
    seq = list(items or [])
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            a, b = seq[i], seq[j]
            pa, pb = _item_conflict_proxy(a), _item_conflict_proxy(b)
            state = detect_structured_conflict(pa, pb)
            if state not in _UNRESOLVED:
                continue
            stmt_differs = (pa.get("normalized_statement") or "") != (
                pb.get("normalized_statement") or ""
            )
            safety_differs = (pa.get("medical_safety_state") or "") != (
                pb.get("medical_safety_state") or ""
            )
            if not (stmt_differs or safety_differs):
                continue
            hits.append(
                RetrievalSetConflictHit(
                    left_canonical_unit_id=str(getattr(a, "canonical_unit_id", "")),
                    right_canonical_unit_id=str(getattr(b, "canonical_unit_id", "")),
                    left_immutable_version_id=str(getattr(a, "immutable_version_id", "")),
                    right_immutable_version_id=str(getattr(b, "immutable_version_id", "")),
                    conflict_state=state.value,
                    left_ku_id=getattr(a, "knowledge_unit_id", None),
                    right_ku_id=getattr(b, "knowledge_unit_id", None),
                )
            )
    return tuple(hits)


def evaluate_retrieval_sufficiency(
    items: Sequence[Any],
    *,
    personal_history_intent: bool = False,
) -> SufficiencyDecision:
    """Retrieval sufficiency only — not diagnosis or emergency classification."""
    if personal_history_intent:
        return SufficiencyDecision(
            sufficient=False,
            reason=SUFFICIENCY_PERSONAL_HISTORY_BLOCKED,
            clarification_required=True,
        )

    seq = list(items or [])
    if not seq:
        return SufficiencyDecision(
            sufficient=False,
            reason=SUFFICIENCY_NO_ELIGIBLE,
            clarification_required=True,
        )

    conflicts = detect_retrieval_set_contradictions(seq)
    if conflicts:
        return SufficiencyDecision(
            sufficient=False,
            reason=SUFFICIENCY_UNRESOLVED_CONFLICT,
            clarification_required=True,
            conflict_hits=conflicts,
        )

    strengths = [str(getattr(i, "evidence_strength", "") or "") for i in seq]
    if strengths and all(s == _LOW for s in strengths):
        return SufficiencyDecision(
            sufficient=False,
            reason=SUFFICIENCY_LOW_ONLY,
            clarification_required=True,
        )

    if any(s in _MODERATE_OR_HIGH for s in strengths):
        return SufficiencyDecision(
            sufficient=True,
            reason=SUFFICIENCY_OK,
            clarification_required=False,
        )

    # UNKNOWN / empty / unexpected bands — fail closed.
    return SufficiencyDecision(
        sufficient=False,
        reason=SUFFICIENCY_NO_ELIGIBLE,
        clarification_required=True,
    )
