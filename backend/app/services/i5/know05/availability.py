"""Knowledge availability — SUPERSEDED/WITHDRAWN/RETRACTED/RIGHTS force runtime/RAG false."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


AVAILABILITY_STATES = frozenset(
    {
        "DISCOVERED",
        "SOURCE_AUTHORIZED",
        "FETCHABLE",
        "FETCHED_TRANSIENTLY",
        "NORMALIZED",
        "STORED",
        "PROVENANCE_VERIFIED",
        "GOVERNED",
        "CURRENT",
        "STALE",
        "CONFLICTED",
        "RETRACTED",
        "SUPERSEDED",
        "WITHDRAWN",
        "RUNTIME_ELIGIBLE",
        "STRUCTURED_SEARCHABLE",
        "RAG_ELIGIBLE",
        "RAG_INDEXED",
        "RAG_STALE",
        "RAG_INVALIDATED",
        "BLOCKED_RIGHTS",
        "BLOCKED_SAFETY",
        "COVERAGE_GAP",
    }
)

RETRIEVAL_STRATEGIES = frozenset(
    {
        "STRUCTURED_SQL",
        "STRUCTURED_CONCEPT_LOOKUP",
        "LEXICAL_FTS",
        "SCIS_RAG_SEMANTIC",
        "COMBINED_HYBRID",
    }
)


@dataclass(frozen=True)
class KnowledgeAvailabilityView:
    object_kind: str
    object_id: str
    states: tuple[str, ...]
    source_of_truth_table: str
    retrieval_strategies: tuple[str, ...]
    rag_eligible: bool
    runtime_eligible: bool
    rights_state: str = "RIGHTS_UNKNOWN"
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "object_kind": self.object_kind,
            "object_id": self.object_id,
            "states": list(self.states),
            "source_of_truth_table": self.source_of_truth_table,
            "retrieval_strategies": list(self.retrieval_strategies),
            "rag_eligible": self.rag_eligible,
            "runtime_eligible": self.runtime_eligible,
            "rights_state": self.rights_state,
            "notes": self.notes,
        }


def derive_ku_availability(
    *,
    ku_id: int,
    runtime_eligibility: str,
    retraction_reason: Optional[str],
    freshness_state: Optional[str],
    provenance_complete: bool,
    publication_state: Optional[str] = None,
    has_structured_links: bool = False,
    rag_indexed: bool = False,
    rag_retracted_at_set: bool = False,
    rights_state: str = "RIGHTS_ALLOWED",
) -> KnowledgeAvailabilityView:
    states: list[str] = ["STORED"]
    if provenance_complete:
        states.append("PROVENANCE_VERIFIED")
        states.append("GOVERNED")

    pub = str(publication_state or "").upper()
    superseded_or_withdrawn = pub in {"SUPERSEDED", "WITHDRAWN"}
    if retraction_reason:
        states.append("RETRACTED")
    if pub == "SUPERSEDED":
        states.append("SUPERSEDED")
    if pub == "WITHDRAWN":
        states.append("WITHDRAWN")

    if freshness_state and str(freshness_state).upper() in {"STALE", "COVERED_STALE"}:
        states.append("STALE")
    elif not retraction_reason and not superseded_or_withdrawn:
        states.append("CURRENT")

    rights = (rights_state or "RIGHTS_UNKNOWN").upper()
    if rights in {"RIGHTS_BLOCKED", "RIGHTS_UNKNOWN"}:
        states.append("BLOCKED_RIGHTS")

    # Hard rule: retracted / superseded / withdrawn / rights-blocked cannot be runtime eligible
    claimed_eligible = str(runtime_eligibility).upper() == "ELIGIBLE"
    runtime_ok = (
        claimed_eligible
        and not retraction_reason
        and not superseded_or_withdrawn
        and rights == "RIGHTS_ALLOWED"
        and provenance_complete
    )
    if runtime_ok:
        states.append("RUNTIME_ELIGIBLE")
        states.append("STRUCTURED_SEARCHABLE")
    elif retraction_reason or superseded_or_withdrawn:
        states.append("BLOCKED_SAFETY")

    rag_eligible = runtime_ok and not rag_retracted_at_set
    if rag_eligible:
        states.append("RAG_ELIGIBLE")
    if rag_indexed and rag_eligible:
        states.append("RAG_INDEXED")
    if rag_indexed and not rag_eligible:
        states.append("RAG_INVALIDATED")

    strategies: list[str] = []
    if runtime_ok:
        strategies.append("STRUCTURED_SQL")
        if has_structured_links:
            strategies.append("STRUCTURED_CONCEPT_LOOKUP")
        if rag_eligible:
            strategies.extend(["LEXICAL_FTS", "SCIS_RAG_SEMANTIC", "COMBINED_HYBRID"])
    elif provenance_complete:
        # Still queryable for audit but not runtime-serving
        strategies.append("STRUCTURED_SQL")

    return KnowledgeAvailabilityView(
        object_kind="KNOWLEDGE_UNIT",
        object_id=str(ku_id),
        states=tuple(dict.fromkeys(states)),
        source_of_truth_table="knowledge_units",
        retrieval_strategies=tuple(dict.fromkeys(strategies)),
        rag_eligible=rag_eligible,
        runtime_eligible=runtime_ok,
        rights_state=rights,
    )


def assert_runtime_eligible_has_retrieval(view: KnowledgeAvailabilityView) -> None:
    if view.runtime_eligible and not view.retrieval_strategies:
        raise ValueError("RUNTIME_ELIGIBLE_NO_RETRIEVAL_PATH")
