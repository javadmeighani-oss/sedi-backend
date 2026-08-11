"""Coverage-driven gap generation — MISSING/PARTIAL/STALE/CONFLICTED → KnowledgeGap."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    CoverageCellState,
    KnowledgeGapPriority,
    KnowledgeGapSeverity,
    KnowledgeGapStatus,
    KnowledgeGapType,
    KnowledgeGapUrgency,
    SediCoveragePriority,
)


P0_CONCEPT_KEYS = frozenset({"ALS", "MS", "DIABETES", "T1D", "T2D", "GDM", "PREDIABETES"})

_CELL_TO_GAP = frozenset(
    {
        CoverageCellState.MISSING.value,
        CoverageCellState.PARTIAL.value,
        CoverageCellState.COVERED_STALE.value,
        CoverageCellState.CONFLICTED.value,
    }
)


@dataclass
class CoveragePrioritizationItem:
    cell_id: int
    concept_id: int
    dimension_code: str
    evidence_class: Optional[str]
    cell_state: str
    priority: str
    p0_overlay: bool
    gap_key: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "concept_id": self.concept_id,
            "dimension_code": self.dimension_code,
            "evidence_class": self.evidence_class,
            "cell_state": self.cell_state,
            "priority": self.priority,
            "p0_overlay": self.p0_overlay,
            "gap_key": self.gap_key,
        }


def _gap_key(concept_id: int, dimension_code: str, evidence_class: Optional[str], cell_state: str) -> str:
    raw = f"cov:{concept_id}:{dimension_code}:{evidence_class or '-'}:{cell_state}"
    return "gap:" + hashlib.sha256(raw.encode()).hexdigest()[:32]


def _is_p0_concept(db: Session, concept_id: int) -> bool:
    c = db.query(models.I5ClinicalConcept).filter_by(id=concept_id).first()
    if c is None:
        return False
    key = (c.concept_key or "").upper()
    if key in P0_CONCEPT_KEYS or any(k in key for k in ("ALS", "MS", "DIABETES")):
        return True
    ov = (
        db.query(models.I5SediPriorityOverlay)
        .filter_by(concept_id=concept_id, priority_class=SediCoveragePriority.P0_CRITICAL.value)
        .first()
    )
    if ov is not None:
        return True
    return False


def prioritize_coverage_cells(db: Session, *, limit: int = 100) -> list[CoveragePrioritizationItem]:
    cells = (
        db.query(models.I5KnowledgeCoverageCell)
        .filter(models.I5KnowledgeCoverageCell.cell_state.in_(list(_CELL_TO_GAP)))
        .order_by(models.I5KnowledgeCoverageCell.id.asc())
        .limit(limit * 5)
        .all()
    )
    items: list[CoveragePrioritizationItem] = []
    for cell in cells:
        p0 = _is_p0_concept(db, cell.concept_id)
        priority = KnowledgeGapPriority.P0.value if p0 else KnowledgeGapPriority.P1.value
        items.append(
            CoveragePrioritizationItem(
                cell_id=cell.id,
                concept_id=cell.concept_id,
                dimension_code=cell.dimension_code,
                evidence_class=cell.evidence_class,
                cell_state=cell.cell_state,
                priority=priority,
                p0_overlay=p0,
                gap_key=_gap_key(cell.concept_id, cell.dimension_code, cell.evidence_class, cell.cell_state),
            )
        )
    # P0 first, then MISSING, then others
    rank = {
        CoverageCellState.MISSING.value: 0,
        CoverageCellState.CONFLICTED.value: 1,
        CoverageCellState.COVERED_STALE.value: 2,
        CoverageCellState.PARTIAL.value: 3,
    }
    items.sort(key=lambda x: (0 if x.p0_overlay else 1, rank.get(x.cell_state, 9), x.cell_id))
    return items[:limit]


def ensure_gaps_from_coverage(
    db: Session,
    *,
    items: Optional[Sequence[CoveragePrioritizationItem]] = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Idempotent: MISSING knowledge → KnowledgeGap (never invent content)."""
    items = list(items) if items is not None else prioritize_coverage_cells(db, limit=limit)
    created = 0
    reused = 0
    for it in items:
        existing = db.query(models.KnowledgeGap).filter_by(canonical_gap_key=it.gap_key).first()
        if existing is not None:
            reused += 1
            continue
        gap = models.KnowledgeGap(
            canonical_gap_key=it.gap_key,
            domain=f"concept:{it.concept_id}",
            subdomain=it.dimension_code,
            gap_type=KnowledgeGapType.MISSING.value
            if it.cell_state == CoverageCellState.MISSING.value
            else KnowledgeGapType.STALE.value
            if it.cell_state == CoverageCellState.COVERED_STALE.value
            else KnowledgeGapType.CONFLICTING.value
            if it.cell_state == CoverageCellState.CONFLICTED.value
            else KnowledgeGapType.INSUFFICIENT_COVERAGE.value,
            priority=it.priority,
            severity=KnowledgeGapSeverity.HIGH.value if it.p0_overlay else KnowledgeGapSeverity.MEDIUM.value,
            urgency=KnowledgeGapUrgency.HIGH.value if it.p0_overlay else KnowledgeGapUrgency.NORMAL.value,
            status=KnowledgeGapStatus.OPEN.value,
            title=f"Coverage {it.cell_state} · dim={it.dimension_code}",
            description=(
                f"Generated from i5_knowledge_coverage_cells id={it.cell_id}; "
                f"evidence_class={it.evidence_class or 'ANY'}; model invention forbidden"
            ),
        )
        db.add(gap)
        created += 1
    db.flush()
    return {
        "gaps_created": created,
        "gaps_reused": reused,
        "items_considered": len(items),
        "model_invented_coverage": 0,
        "p0_specific_schema_branching": 0,
    }


def p0_coverage_report(db: Session) -> dict[str, Any]:
    """Disease × dimension × evidence_class × freshness report for ALS/MS/Diabetes."""
    concepts = (
        db.query(models.I5ClinicalConcept)
        .filter(models.I5ClinicalConcept.concept_key.in_(list(P0_CONCEPT_KEYS)))
        .all()
    )
    by_disease: dict[str, list[dict[str, Any]]] = {}
    for c in concepts:
        cells = db.query(models.I5KnowledgeCoverageCell).filter_by(concept_id=c.id).all()
        rows = [
            {
                "dimension": cell.dimension_code,
                "evidence_class": cell.evidence_class,
                "state": cell.cell_state,
                "authority_tier": "UNIVERSAL_TAXONOMY",
            }
            for cell in cells
        ]
        by_disease[c.concept_key] = rows
    return {
        "als": by_disease.get("ALS", []),
        "ms": by_disease.get("MS", []),
        "diabetes": by_disease.get("DIABETES", [])
        + by_disease.get("T1D", [])
        + by_disease.get("T2D", [])
        + by_disease.get("GDM", [])
        + by_disease.get("PREDIABETES", []),
        "fake_completeness": 0,
        "p0_specific_schema_branching": 0,
    }
