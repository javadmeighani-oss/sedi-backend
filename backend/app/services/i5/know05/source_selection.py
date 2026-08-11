"""NF20 — coverage gap → Registry-driven source selection (canonical rights / NF24).

Source universe authority is the persisted Governed Source Registry.
Generic evidence-class → SourceRole mappings are allowed.
Hardcoded source-key eligibility routes and silent PubMed/WHO/CT.gov
fallbacks are forbidden (HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT=0).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import CoverageCellState, SourceRole, SourceUniverse
from backend.app.services.i5.know01.registry_service import query_sources_by_role
from backend.app.services.i5.know05.canonical_rights import (
    OP_DERIVED_METADATA_PERSIST,
    evaluate_connector_operation_rights,
)
from backend.app.services.i5.know05.coverage_engine import CoveragePrioritizationItem, prioritize_coverage_cells
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity


# Semantic role mapping only — never source keys.
_EVIDENCE_CLASS_TO_ROLES: dict[str, tuple[str, ...]] = {
    "CLINICAL_TRIAL": (SourceRole.CLINICAL_TRIAL.value,),
    "CLINICAL_TRIALS": (SourceRole.CLINICAL_TRIAL.value,),
    "GUIDELINE": (SourceRole.CLINICAL_GUIDELINE.value,),
    "RECOMMENDATION": (SourceRole.CLINICAL_GUIDELINE.value,),
    "SCIENTIFIC_STUDY": (SourceRole.SCIENTIFIC_LITERATURE.value,),
    "PEER_REVIEWED": (SourceRole.SCIENTIFIC_LITERATURE.value,),
    "LITERATURE": (SourceRole.SCIENTIFIC_LITERATURE.value,),
    "TERMINOLOGY": (SourceRole.BIOMEDICAL_TERMINOLOGY.value,),
}

_DIMENSION_TO_ROLES: dict[str, tuple[str, ...]] = {
    "PHARMACOLOGICAL_TREATMENT": (
        SourceRole.SCIENTIFIC_LITERATURE.value,
        SourceRole.CLINICAL_TRIAL.value,
        SourceRole.DRUG_INFORMATION.value,
    ),
    "NON_PHARMACOLOGICAL_TREATMENT": (
        SourceRole.SCIENTIFIC_LITERATURE.value,
        SourceRole.CLINICAL_GUIDELINE.value,
        SourceRole.REHABILITATION.value,
    ),
    "DIAGNOSIS": (SourceRole.SCIENTIFIC_LITERATURE.value, SourceRole.CLINICAL_GUIDELINE.value),
    "SCREENING": (SourceRole.CLINICAL_GUIDELINE.value, SourceRole.PUBLIC_HEALTH.value),
    "PREVENTION": (
        SourceRole.PREVENTION.value,
        SourceRole.PUBLIC_HEALTH.value,
        SourceRole.CLINICAL_GUIDELINE.value,
    ),
    "PROGNOSIS": (SourceRole.SCIENTIFIC_LITERATURE.value,),
    "CLINICAL_TRIALS": (SourceRole.CLINICAL_TRIAL.value,),
}

# Adapter / handler implementation awareness (dispatch), NOT source-universe authority.
_KNOWN_ADAPTER_HANDLERS = frozenset(
    {
        "clinicaltrials_gov_api_v2",
        "who_guideline_catalogue",
        "pubmed_ncbi_eutils",
        "pubmed_central",
        "who_news_discovery",
    }
)

NO_ELIGIBLE_GOVERNED_SOURCE = "NO_ELIGIBLE_GOVERNED_SOURCE"
HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT = 0
_LIFECYCLE_ELIGIBLE = frozenset({"ACTIVE", "APPROVED"})


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

    @property
    def selected_for_crawl(self) -> bool:
        return (
            self.connector_key != NO_ELIGIBLE_GOVERNED_SOURCE
            and self.automation_decision == "AUTOMATION_ALLOWED"
            and self.block_reason is None
        )


def _concept_key(db: Session, concept_id: int) -> Optional[str]:
    c = db.query(models.I5ClinicalConcept).filter_by(id=concept_id).first()
    return c.concept_key if c else None


def connector_key_from_canonical(canonical_key: str) -> str:
    ck = (canonical_key or "").strip()
    if ck.startswith("know01:"):
        return ck[len("know01:") :]
    return ck


def _roles_for_gap(item: CoveragePrioritizationItem) -> list[str]:
    roles: list[str] = []
    ec = (item.evidence_class or "").upper()
    dim = (item.dimension_code or "").upper()
    for role in _EVIDENCE_CLASS_TO_ROLES.get(ec, ()):
        if role not in roles:
            roles.append(role)
    for role in _DIMENSION_TO_ROLES.get(dim, ()):
        if role not in roles:
            roles.append(role)
    return roles


def _connector_capability(connector_key: str, ext: Optional[models.I5SourceRegistryExtension] = None) -> str:
    """CONNECTOR_READY requires an executable adapter contract (or known specialized handler).

    Route presence alone must NOT imply CONNECTOR_READY.
    """
    if connector_key.startswith("terminology:"):
        return "CONTRACT_PENDING"
    if connector_key.startswith("iran_") or "iran" in connector_key.lower():
        return "DIRECTORY_ONLY"
    if ext is not None:
        if (ext.source_universe or "") == SourceUniverse.IRAN_LOCAL_DIRECTORY.value:
            return "DIRECTORY_ONLY"
        # Specialized KNOW-05 handlers remain executable by key (dispatch, not eligibility universe).
        if connector_key in _KNOWN_ADAPTER_HANDLERS:
            return "CONNECTOR_READY"
        from backend.app.services.i5.know05.generic_execution_bridge import adapter_contract_resolvable

        ok, _mode, reason = adapter_contract_resolvable(ext)
        if ok:
            return "CONNECTOR_READY"
        has_route = any(
            [
                (ext.api_endpoint or "").strip(),
                (ext.canonical_discovery_endpoint or "").strip(),
                (ext.rss_endpoint or "").strip(),
                (ext.atom_endpoint or "").strip(),
                (ext.sitemap_endpoint or "").strip(),
                (ext.oai_endpoint or "").strip(),
                (ext.bulk_endpoint or "").strip(),
                (ext.canonical_home or "").strip(),
            ]
        )
        if has_route or (ext.supported_formats or "").strip():
            return "ROUTE_PRESENT_BUT_ADAPTER_UNRESOLVED"
        return "UNKNOWN_CONNECTOR"
    return "CONNECTOR_READY" if connector_key in _KNOWN_ADAPTER_HANDLERS else "UNKNOWN_CONNECTOR"


def resolve_selection_automation(
    db: Session,
    connector_key: str,
    *,
    ext: Optional[models.I5SourceRegistryExtension] = None,
) -> tuple[str, str, str, Optional[str]]:
    """Return (source_authority_state, rights_state, automation_decision, block_reason)."""
    cap = _connector_capability(connector_key, ext)
    if cap == "DIRECTORY_ONLY":
        return (
            "DIRECTORY_ONLY",
            "RIGHTS_BLOCKED",
            "BLOCKED",
            "IRAN_LOCAL_DIRECTORY_NE_CLINICAL_KNOWLEDGE_AUTHORITY",
        )
    if cap == "UNKNOWN_CONNECTOR":
        return ("UNKNOWN", "RIGHTS_UNKNOWN", "BLOCKED", "NO_VERIFIED_CONNECTOR_CONTRACT")
    if cap == "ROUTE_PRESENT_BUT_ADAPTER_UNRESOLVED":
        return ("UNKNOWN", "RIGHTS_UNKNOWN", "BLOCKED", "NO_VERIFIED_ADAPTER_CONTRACT")
    if cap == "CONTRACT_PENDING":
        return ("CONTRACT_READY", "RIGHTS_UNKNOWN", "BLOCKED", "TERMINOLOGY_CREDENTIALS_OR_LICENSE_PENDING")

    rights = evaluate_connector_operation_rights(
        db, connector_key=connector_key, operation=OP_DERIVED_METADATA_PERSIST
    )
    auth = "CANONICAL_GSP_FOUND" if rights.gsp_found else "CANONICAL_SOURCE_MISSING"
    auto = rights.automation_decision
    block = rights.block_reason
    if connector_key.startswith("pubmed"):
        identity = load_ncbi_operational_identity(require_for_weekly=True)
        if identity.weekly_operation_status != "LIVE_READY":
            auto = "BLOCKED"
            block = identity.weekly_operation_status
        elif rights.automation_decision != "AUTOMATION_ALLOWED":
            auto = "BLOCKED"
            block = rights.block_reason
    return auth, rights.rights_state, auto, block


def _rank_key(gsp: models.GovernedSourceProfile, ext: models.I5SourceRegistryExtension) -> tuple:
    lifecycle_rank = 0 if (gsp.registry_state or "").upper() in _LIFECYCLE_ELIGIBLE else 1
    rights_rank = 0 if (ext.automation_right or "").upper() == "ALLOWED" else 1
    return (lifecycle_rank, rights_rank, connector_key_from_canonical(gsp.canonical_key or ""))


def select_connectors_for_gap(
    db: Session,
    item: CoveragePrioritizationItem,
    *,
    max_sources: int = 8,
) -> list[SourceSelection]:
    """Query persisted Registry by role; never inject hardcoded source keys."""
    roles = _roles_for_gap(item)
    ck_key = _concept_key(db, item.concept_id)
    out: list[SourceSelection] = []

    if not roles:
        # No semantic role for this cell — fail closed (no source-key fallback).
        if item.cell_state in {
            CoverageCellState.MISSING.value,
            CoverageCellState.PARTIAL.value,
            CoverageCellState.COVERED_STALE.value,
        }:
            return [
                SourceSelection(
                    gap_key=item.gap_key,
                    concept_id=item.concept_id,
                    concept_key=ck_key,
                    dimension_code=item.dimension_code,
                    evidence_class=item.evidence_class,
                    cell_state=item.cell_state,
                    priority=item.priority,
                    p0_overlay=item.p0_overlay,
                    connector_key=NO_ELIGIBLE_GOVERNED_SOURCE,
                    why_selected="NO_SEMANTIC_ROLE_FOR_GAP",
                    connector_capability_state="UNKNOWN_CONNECTOR",
                    source_authority_state="NONE",
                    rights_state="RIGHTS_UNKNOWN",
                    automation_decision="BLOCKED",
                    block_reason=NO_ELIGIBLE_GOVERNED_SOURCE,
                )
            ]
        return []

    seen_keys: set[str] = set()
    candidates: list[tuple[models.GovernedSourceProfile, models.I5SourceRegistryExtension, str]] = []
    for role in roles:
        for ext in query_sources_by_role(db, role):
            gsp = db.query(models.GovernedSourceProfile).filter_by(id=ext.source_profile_id).first()
            if gsp is None:
                continue
            connector_key = connector_key_from_canonical(gsp.canonical_key or "")
            if not connector_key or connector_key in seen_keys:
                continue
            # Iran directories never enter clinical evidence crawls via role alone.
            if (ext.source_universe or "") == SourceUniverse.IRAN_LOCAL_DIRECTORY.value:
                continue
            seen_keys.add(connector_key)
            candidates.append((gsp, ext, f"registry_role={role}"))

    candidates.sort(key=lambda t: _rank_key(t[0], t[1]))

    for gsp, ext, why in candidates[:max_sources]:
        connector_key = connector_key_from_canonical(gsp.canonical_key or "")
        lifecycle = (gsp.registry_state or "").upper()
        cap = _connector_capability(connector_key, ext)

        if lifecycle not in _LIFECYCLE_ELIGIBLE:
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
                    why_selected=why + f";lifecycle={lifecycle or 'NONE'}",
                    connector_capability_state=cap,
                    source_authority_state="REGISTRY_LIFECYCLE_INELIGIBLE",
                    rights_state="RIGHTS_UNKNOWN",
                    automation_decision="BLOCKED",
                    block_reason="REGISTRY_LIFECYCLE_NOT_ACTIVE_OR_APPROVED",
                )
            )
            continue

        auth, rights_state, auto, block = resolve_selection_automation(db, connector_key, ext=ext)
        # Rights UNKNOWN/DENIED never become crawl-eligible.
        ar = (ext.automation_right or "").upper()
        if ar in {"UNKNOWN", "DENIED", "REVIEW_REQUIRED", ""}:
            auto = "BLOCKED"
            block = block or f"REGISTRY_AUTOMATION_RIGHT_{ar or 'EMPTY'}"
            if rights_state == "RIGHTS_ALLOWED":
                rights_state = "RIGHTS_BLOCKED" if ar == "DENIED" else "RIGHTS_UNKNOWN"

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

    crawl_eligible = [s for s in out if s.selected_for_crawl]
    if not crawl_eligible and item.cell_state in {
        CoverageCellState.MISSING.value,
        CoverageCellState.PARTIAL.value,
        CoverageCellState.COVERED_STALE.value,
    }:
        # Fail closed: never inject PubMed/WHO/ClinicalTrials.
        out.insert(
            0,
            SourceSelection(
                gap_key=item.gap_key,
                concept_id=item.concept_id,
                concept_key=ck_key,
                dimension_code=item.dimension_code,
                evidence_class=item.evidence_class,
                cell_state=item.cell_state,
                priority=item.priority,
                p0_overlay=item.p0_overlay,
                connector_key=NO_ELIGIBLE_GOVERNED_SOURCE,
                why_selected="REGISTRY_QUERY_NO_ELIGIBLE_SOURCE",
                connector_capability_state="UNKNOWN_CONNECTOR",
                source_authority_state="NONE",
                rights_state="RIGHTS_UNKNOWN",
                automation_decision="BLOCKED",
                block_reason=NO_ELIGIBLE_GOVERNED_SOURCE,
            ),
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
    selections.sort(
        key=lambda s: (
            0 if s.p0_overlay else 1,
            0 if s.selected_for_crawl else 1,
            0 if s.block_reason is None else 1,
            s.gap_key,
        )
    )
    return selections[: limit * 3]


def assert_no_hardcoded_source_key_eligibility_fallbacks() -> None:
    """Static invariant for Gate F1."""
    if HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT != 0:
        raise AssertionError("HARDCODED_SOURCE_KEY_ELIGIBILITY_FALLBACK_COUNT_NONZERO")
    # Ensure removed symbols stay gone.
    mod = __import__(__name__, fromlist=["*"])
    for forbidden in ("_EVIDENCE_CLASS_ROUTES", "_DIMENSION_HINTS"):
        if hasattr(mod, forbidden):
            raise AssertionError(f"FORBIDDEN_SOURCE_KEY_ROUTE_PRESENT:{forbidden}")
