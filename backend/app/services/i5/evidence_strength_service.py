"""I5-IMPL-W2-P02 — pure evidence-strength validation / classification (no DB)."""
from __future__ import annotations

from typing import Optional, Union

from backend.app.services.i5.enums import EvidenceStrength

_AUTHORITATIVE_TIERS = frozenset({"AUTHORITATIVE", "HIGH"})


class EvidenceStrengthServiceError(ValueError):
    """Fail-closed validation error for evidence-strength helpers."""


def validate_evidence_strength(value: Union[str, EvidenceStrength]) -> EvidenceStrength:
    """Parse and validate a persisted evidence-strength literal."""
    if value is None:
        raise EvidenceStrengthServiceError("EVIDENCE_STRENGTH_REQUIRED")
    if isinstance(value, EvidenceStrength):
        return value
    try:
        return EvidenceStrength(str(value))
    except ValueError as exc:
        raise EvidenceStrengthServiceError(f"EVIDENCE_STRENGTH_INVALID:{value}") from exc


def classify_evidence_strength(
    *,
    source_authority_tier: Optional[str],
    has_guideline: bool,
    has_conflict: bool,
    assessed: bool,
) -> EvidenceStrength:
    """Deterministic minimal evidence-strength classifier (fail-closed when unassessed)."""
    if not assessed:
        return EvidenceStrength.UNKNOWN
    if has_conflict:
        return EvidenceStrength.CONFLICTED
    tier = (source_authority_tier or "").strip().upper()
    if has_guideline and tier in _AUTHORITATIVE_TIERS:
        return EvidenceStrength.HIGH
    if has_guideline:
        return EvidenceStrength.MODERATE
    return EvidenceStrength.LOW
