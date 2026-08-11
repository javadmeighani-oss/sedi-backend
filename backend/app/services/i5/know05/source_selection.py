"""NF20 — coverage gap → source family selection (no model-invented authority)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import CoverageCellState
from backend.app.services.i5.know05.coverage_engine import CoveragePrioritizationItem, prioritize_coverage_cells
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity


# Semantic routing derived from KNOW-04 connector contracts (not invented authorities).
_EVIDENCE_CLASS_ROUTES: dict[str, tuple[str, ...]] = {
    "CLINICAL_TRIAL": ("clinicaltrials_gov_api_v2",),
    "CLINICAL_TRIALS": ("clinicaltrials_gov_api_v2",),
    "GUIDELINE": ("who_guideline_catalogue",),
    "RECOMMENDATION": ("who_guideline_catalogue",),
    "SCIENTIFIC_STUDY": ("pubmed_ncbi_eutils", "pubmed_central"),
    "PEER_REVIEWED": ("pubmed_ncbi_eutils", "pubmed_central"),
    "LITERATURE": ("pubmed_ncbi_eutils", "pubmed_central"),
    "TERMINOLOGY": ("terminology:mesh",),
}

_DIMENSION_HINTS: dict[str, tuple[str, ...]] = {
    "PHARMACOLOGICAL_TREATMENT": ("pubmed_ncbi_eutils", "clinicaltrials_gov_api_v2"),
    "NON_PHARMACOLOGICAL_TREATMENT": ("pubmed_ncbi_eutils", "who_guideline_catalogue"),
    "DIAGNOSIS": ("pubmed_ncbi_eutils", "who_guideline_catalogue"),
    "SCREENING": ("who_guideline_catalogue", "pubmed_ncbi_eutils"),
    "PREVENTION": ("who_guideline_catalogue", "pubmed_ncbi_eutils"),
    "PROGNOSIS": ("pubmed_ncbi_eutils",),
    "CLINICAL_TRIALS": ("clinicaltrials_gov_api_v2",),
}


@dataclass
class SourceSelection:
    gap_key: str
    concept_id: int
    concept_key: Optional[str]
    dimension_code: str
    evidence_class: Optional[str]
    cell_state: str
    priority: str
    p0_overlay: bool
    connector_key: str
    why_selected: str
    authority_state: str
    rights_state: str
    automation_state: str
    block_reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "gap_key": self.gap_key,
            "concept_id": self.concept_id,
            "concept_key": self.concept_key,
            "dimension": self.dimension_code,
            "evidence_class": self.evidence_class,
            "cell_state": self.cell_state,
            "priority": self.priority,
            "p0_overlay": self.p0_overlay,
            "selected_connector": self.connector_key,
            "why_selected": self.why_selected,
            "authority_state": self.authority_state,
            "rights_state": self.rights_state,
            "automation_state": self.automation_state,
            "block_reason": self.block_reason,
        }


def _concept_key(db: Session, concept_id: int) -> Optional[str]:
    c = db.query(models.I5ClinicalConcept).filter_by(id=concept_id).first()
    return c.concept_key if c else None


def _connector_automation_state(connector_key: str) -> tuple[str, str, Optional[str]]:
    """Return (authority_state, automation_state, block_reason)."""
    if connector_key.startswith("pubmed"):
        identity = load_ncbi_operational_identity(require_for_weekly=True)
        if identity.weekly_operation_status != "LIVE_READY":
            return (
                "CONNECTOR_READY",
                "BLOCKED",
                identity.weekly_operation_status,
            )
        return ("CONNECTOR_READY", "AUTOMATION_ALLOWED", None)
    if connector_key.startswith("terminology:"):
        return ("CONTRACT_READY", "BLOCKED", "TERMINOLOGY_CREDENTIALS_OR_LICENSE_PENDING")
    if connector_key == "clinicaltrials_gov_api_v2":
        return ("CONNECTOR_READY", "AUTOMATION_ALLOWED", None)
    if connector_key == "who_guideline_catalogue":
        return ("CONNECTOR_READY", "AUTOMATION_ALLOWED", None)
    if connector_key.startswith("iran_") or "iran" in connector_key.lower():
        return (
            "DIRECTORY_ONLY",
            "BLOCKED",
            "IRAN_LOCAL_DIRECTORY_NE_CLINICAL_KNOWLEDGE_AUTHORITY",
        )
    return ("UNKNOWN_CONNECTOR", "BLOCKED", "NO_VERIFIED_CONNECTOR_CONTRACT")


def select_connectors_for_gap(
    db: Session,
    item: CoveragePrioritizationItem,
) -> list[SourceSelection]:
    """Map one coverage-derived gap to appropriate connector families."""
    ec = (item.evidence_class or "").upper()
    dim = (item.dimension_code or "").upper()
    candidates: list[tuple[str, str]] = []

    for ck in _EVIDENCE_CLASS_ROUTES.get(ec, ()):
        candidates.append((ck, f"evidence_class={ec}"))
    for ck in _DIMENSION_HINTS.get(dim, ()):
        if not any(c[0] == ck for c in candidates):
            candidates.append((ck, f"dimension={dim}"))

    # Fallback for MISSING cells without evidence class: literature + guidelines + trials
    if not candidates and item.cell_state in {
        CoverageCellState.MISSING.value,
        CoverageCellState.PARTIAL.value,
        CoverageCellState.COVERED_STALE.value,
    }:
        candidates = [
            ("pubmed_ncbi_eutils", "fallback_missing_literature"),
            ("who_guideline_catalogue", "fallback_missing_guideline"),
            ("clinicaltrials_gov_api_v2", "fallback_missing_trials"),
        ]

    ck_key = _concept_key(db, item.concept_id)
    out: list[SourceSelection] = []
    for connector_key, why in candidates:
        auth, auto, block = _connector_automation_state(connector_key)
        rights = "RIGHTS_ALLOWED" if auto == "AUTOMATION_ALLOWED" else "RIGHTS_BLOCKED_OR_PENDING"
        out.append(
            SourceSelection(
                gap_key=item.gap_key,
                concept_id=item.concept_id,
                concept_key=ck_key,
                dimension_code=item.dimension_code,
                evidence_class=item.evidence_class,
                cell_state=item.cell_state,
                priority=item.priority,
                p0_overlay=item.p0_overlay,
                connector_key=connector_key,
                why_selected=why,
                authority_state=auth,
                rights_state=rights,
                automation_state=auto,
                block_reason=block,
            )
        )
    return out


def select_sources_for_coverage(
    db: Session,
    *,
    limit: int = 20,
    items: Optional[Sequence[CoveragePrioritizationItem]] = None,
) -> list[SourceSelection]:
    items = list(items) if items is not None else prioritize_coverage_cells(db, limit=limit)
    selections: list[SourceSelection] = []
    for it in items:
        selections.extend(select_connectors_for_gap(db, it))
    # Prefer P0 + unblocked
    selections.sort(key=lambda s: (0 if s.p0_overlay else 1, 0 if s.block_reason is None else 1, s.gap_key))
    return selections[: limit * 3]
