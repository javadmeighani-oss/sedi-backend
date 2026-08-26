"""Conflict / negative-evidence labeling for KNOW-07 bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from backend.app.services.i5.enums import EvidenceSupportDirection
from backend.app.services.i5.know07 import CONFLICT_GROUPING_KEYS, SUPPORT_DIRECTIONS


@dataclass(frozen=True)
class ConflictGroupContext:
    disease: Optional[str] = None
    population: Optional[str] = None
    intervention: Optional[str] = None
    comparator: Optional[str] = None
    outcome: Optional[str] = None
    time_horizon: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in CONFLICT_GROUPING_KEYS}


@dataclass
class LabeledEvidenceRelation:
    support_direction: str
    conflict_group: ConflictGroupContext = field(default_factory=ConflictGroupContext)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "support_direction": self.support_direction,
            "conflict_group": self.conflict_group.as_dict(),
            "note": self.note,
        }


def normalize_support_direction(value: Optional[str]) -> str:
    token = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    # Map weak supports into SUPPORTS for bundle contract; keep exact required set.
    if token in {"WEAKLY_SUPPORTS", "SUPPORT"}:
        token = EvidenceSupportDirection.SUPPORTS.value
    if token in {"NEUTRAL", ""}:
        token = EvidenceSupportDirection.INCONCLUSIVE.value
    if token not in SUPPORT_DIRECTIONS:
        raise ValueError(f"UNKNOWN_SUPPORT_DIRECTION:{token}")
    return token


def label_evidence_relation(
    *,
    support_direction: str,
    conflict_group: Optional[Mapping[str, Any]] = None,
    note: str = "",
) -> LabeledEvidenceRelation:
    direction = normalize_support_direction(support_direction)
    cg_raw = conflict_group or {}
    group = ConflictGroupContext(**{k: cg_raw.get(k) for k in CONFLICT_GROUPING_KEYS})
    return LabeledEvidenceRelation(support_direction=direction, conflict_group=group, note=note)


def collapse_forbidden(relations: list[LabeledEvidenceRelation]) -> None:
    """Do not collapse contradictory evidence into one false consensus."""
    dirs = {r.support_direction for r in relations}
    if {"SUPPORTS", "CONTRADICTS"} <= dirs or {"SUPPORTS", "REFUTES"} <= dirs:
        # Caller must retain separate labeled items — never merge to SUPPORTS.
        if len(relations) < 2:
            raise ValueError("CONFLICT_COLLAPSE_FORBIDDEN")
