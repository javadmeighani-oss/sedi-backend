"""NF20 — coverage gap → source family selection with canonical rights (NF24)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import CoverageCellState
from backend.app.services.i5.know05.canonical_rights import (
    OP_DERIVED_METADATA_PERSIST,
    OP_NETWORK_FETCH,
    evaluate_connector_operation_rights,
)
from backend.app.services.i5.know05.coverage_engine import CoveragePrioritizationItem, prioritize_coverage_cells
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity


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
    connector_capability_state: str
    source_authority_state: str
    rights_state: str
    automation_decision: str
    block_reason: Optional[str] = None
    # Back-compat aliases used by orchestrator/tests
    authority_state: str = ""
    automation_state: str = ""

    def __post_init__(self) -> None:
        if not self.authority_state:
            self.authority_state = self.source_authority_state
        if not self.automation_state:
            self.automation_state = self.automation_decision

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
            "connector_capability_state": self.connector_capability_state,
            "source_authority_state": self.source_authority_state,
            "authority_state": self.authority_state,
            "rights_state": self.rights_state,
            "automation_decision": self.automation_decision,
            "automation_state": self.automation_state,
            "block_reason": self.block_reason,
        }


def _concept_key(db: Session, concept_id: int) -> Optional[str]:
    c = db.query(models.I5ClinicalConcept).filter_by(id=concept_id).first()
    return c.concept_key if c else None


def _connector_capability(connector_key: str) -> str:
    if connector_key.startswith("terminology:"):
        return "CONTRACT_PENDING"
    if connector_key.startswith("iran_") or "iran" in connector_key.lower():
        return "DIRECTORY_ONLY"
    known = {
        "clinicaltrials_gov_api_v2",
        "who_guideline_catalogue",
        "pubmed_ncbi_eutils",
        "pubmed_central",
        "who_news_discovery",
    }
    return "CONNECTOR_READY" if connector_key in known else "UNKNOWN_CONNECTOR"


def resolve_selection_automation(db: Session, connector_key: str) -> tuple[str, str, str, Optional[str]]:
    """Return (source_authority_state, rights_state, automation_decision, block_reason)."""
    cap = _connector_capability(connector_key)
    if cap == "DIRECTORY_ONLY":
        return (
            "DIRECTORY_ONLY",
            "RIGHTS_BLOCKED",
            "BLOCKED",
            "IRAN_LOCAL_DIRECTORY_NE_CLINICAL_KNOWLEDGE_AUTHORITY",
        )
    if cap == "UNKNOWN_CONNECTOR":
        return ("UNKNOWN", "RIGHTS_UNKNOWN", "BLOCKED", "NO_VERIFIED_CONNECTOR_CONTRACT")
    if cap == "CONTRACT_PENDING":
        return ("CONTRACT_READY", "RIGHTS_UNKNOWN", "BLOCKED", "TERMINOLOGY_CREDENTIALS_OR_LICENSE_PENDING")

    rights = evaluate_connector_operation_rights(
        db, connector_key=connector_key, operation=OP_DERIVED_METADATA_PERSIST
    )
    auth = "CANONICAL_GSP_FOUND" if rights.gsp_found else "CANONICAL_SOURCE_MISSING"
    auto = rights.automation_decision
    block = rights.block_reason
    # PubMed: rights AND operational identity
    if connector_key.startswith("pubmed"):
        identity = load_ncbi_operational_identity(require_for_weekly=True)
        if identity.weekly_operation_status != "LIVE_READY":
            auto = "BLOCKED"
            block = identity.weekly_operation_status
            # Keep rights_state distinct from identity gate
        elif rights.automation_decision != "AUTOMATION_ALLOWED":
            auto = "BLOCKED"
            block = rights.block_reason
    return auth, rights.rights_state, auto, block


def select_connectors_for_gap(
    db: Session,
    item: CoveragePrioritizationItem,
) -> list[SourceSelection]:
    ec = (item.evidence_class or "").upper()
    dim = (item.dimension_code or "").upper()
    candidates: list[tuple[str, str]] = []

    for ck in _EVIDENCE_CLASS_ROUTES.get(ec, ()):
        candidates.append((ck, f"evidence_class={ec}"))
    for ck in _DIMENSION_HINTS.get(dim, ()):
        if not any(c[0] == ck for c in candidates):
            candidates.append((ck, f"dimension={dim}"))

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
        cap = _connector_capability(connector_key)
        auth, rights_state, auto, block = resolve_selection_automation(db, connector_key)
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
                connector_capability_state=cap,
                source_authority_state=auth,
                rights_state=rights_state,
                automation_decision=auto,
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
    selections.sort(key=lambda s: (0 if s.p0_overlay else 1, 0 if s.block_reason is None else 1, s.gap_key))
    return selections[: limit * 3]
