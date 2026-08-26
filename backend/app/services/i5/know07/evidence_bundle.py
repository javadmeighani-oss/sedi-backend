"""Evidence-aware retrieval + labeled evidence bundle (GLOBAL_GOVERNED_KNOWLEDGE)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.services.i5.know07 import (
    GLOBAL_GOVERNED_KNOWLEDGE_LABEL,
    PURE_VECTOR_ONLY_RAG_ALLOWED,
)
from backend.app.services.i5.know07.conflict import LabeledEvidenceRelation, label_evidence_relation
from backend.app.services.i5.know07.exclusions import assert_cannot_reenter, hard_exclude_ku
from backend.app.services.scis.contracts import (
    RetrievalMode,
    ScisEvidenceItem,
    ScisRetrievalRequest,
    ScisRetrievalResponse,
)
from backend.app.services.scis.retrieval import retrieve as scis_retrieve


@dataclass
class EvidenceBundleItem:
    label: str
    knowledge_unit_id: Optional[int]
    content: str
    evidence_strength: Optional[str]
    evidence_type: Optional[str]
    freshness_state: Optional[str]
    publication_state: Optional[str]
    conflict_state: Optional[str]
    support_direction: Optional[str]
    eligibility_state: Optional[str]
    provenance: Dict[str, Any]
    source_attribution: Optional[str]
    citation: Optional[str]
    uncertainty_safety: Dict[str, Any]
    conflict_relation: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "knowledge_unit_id": self.knowledge_unit_id,
            "content": self.content,
            "evidence_strength": self.evidence_strength,
            "evidence_type": self.evidence_type,
            "freshness_state": self.freshness_state,
            "publication_state": self.publication_state,
            "conflict_state": self.conflict_state,
            "support_direction": self.support_direction,
            "eligibility_state": self.eligibility_state,
            "provenance": self.provenance,
            "source_attribution": self.source_attribution,
            "citation": self.citation,
            "uncertainty_safety": self.uncertainty_safety,
            "conflict_relation": self.conflict_relation,
            "metadata": self.metadata,
        }


@dataclass
class EvidenceBundle:
    query: str
    intent: Optional[str]
    domain: Optional[str]
    knowledge_plane: str
    items: List[EvidenceBundleItem]
    filtered_counts: Dict[str, int]
    retrieval_mode: str
    fallback_state: str
    uncertainty_safety: Dict[str, Any]
    request_trace_id: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "domain": self.domain,
            "knowledge_plane": self.knowledge_plane,
            "items": [i.as_dict() for i in self.items],
            "filtered_counts": dict(self.filtered_counts),
            "retrieval_mode": self.retrieval_mode,
            "fallback_state": self.fallback_state,
            "uncertainty_safety": self.uncertainty_safety,
            "request_trace_id": self.request_trace_id,
        }


def _forbid_pure_vector(mode: RetrievalMode) -> None:
    if mode == RetrievalMode.VECTOR and not PURE_VECTOR_ONLY_RAG_ALLOWED:
        raise ValueError("PURE_VECTOR_ONLY_RAG_FORBIDDEN")


def _ku_from_item_meta(item: ScisEvidenceItem) -> dict[str, Any]:
    md = item.metadata or {}
    return {
        "provenance_complete": md.get("ku_provenance_complete", True),
        "evidence_strength": md.get("ku_evidence_strength") or md.get("evidence_strength"),
        "freshness_state": md.get("ku_freshness_state") or md.get("freshness_state"),
        "conflict_state": md.get("ku_conflict_state") or md.get("conflict_state"),
        "medical_safety_state": md.get("ku_medical_safety_state") or md.get("medical_safety_state"),
        "publication_state": md.get("ku_publication_state") or md.get("publication_state"),
        "retraction_reason": md.get("ku_retraction_reason") or md.get("retraction_reason"),
        "runtime_eligibility": item.runtime_eligibility,
    }


def enrich_scis_item_metadata(item: ScisEvidenceItem, payload_hints: Optional[Mapping] = None) -> ScisEvidenceItem:
    """Attach KU structured fields into item.metadata when provided by retrieval payload."""
    hints = dict(payload_hints or {})
    item.metadata = {**(item.metadata or {}), **hints}
    return item


def build_evidence_bundle_from_scis(
    response: ScisRetrievalResponse,
    *,
    query: str,
    intent: Optional[str] = None,
    domain: Optional[str] = None,
    support_labels: Optional[Sequence[LabeledEvidenceRelation]] = None,
) -> EvidenceBundle:
    items: List[EvidenceBundleItem] = []
    filtered = dict(response.filtered_counts or {})
    labels = list(support_labels or [])

    for idx, ev in enumerate(response.evidence):
        if ev.label != GLOBAL_GOVERNED_KNOWLEDGE_LABEL:
            filtered["non_global_label"] = filtered.get("non_global_label", 0) + 1
            continue
        ku_proxy = _ku_from_item_meta(ev)
        excl = hard_exclude_ku(ku_proxy, retracted_at=(ev.metadata or {}).get("retracted_at"))
        if excl.excluded:
            filtered[excl.code] = filtered.get(excl.code, 0) + 1
            # Prove silent re-entry is forbidden for every branch.
            for branch in ("lexical", "vector", "hybrid", "fallback"):
                try:
                    assert_cannot_reenter(branch=branch, exclusion=excl)
                except ValueError:
                    pass
            continue

        rel = labels[idx].as_dict() if idx < len(labels) else None
        support_dir = rel["support_direction"] if rel else (ev.metadata or {}).get("support_direction")
        if support_dir:
            support_dir = label_evidence_relation(support_direction=str(support_dir)).support_direction

        prov = {
            "chunk_id": ev.provenance.chunk_id if ev.provenance else None,
            "knowledge_unit_id": ev.knowledge_unit_id,
            "immutable_version_id": ev.immutable_version_id,
            "raw_evidence_id": ev.provenance.raw_evidence_id if ev.provenance else None,
            "source_profile_id": ev.provenance.source_profile_id if ev.provenance else None,
            "locator": ev.provenance.locator if ev.provenance else None,
        }
        if not any([prov.get("knowledge_unit_id"), prov.get("raw_evidence_id"), prov.get("source_profile_id")]):
            filtered["citation_integrity_fail"] = filtered.get("citation_integrity_fail", 0) + 1
            continue

        uncertainty = {
            "medical_safety_state": ku_proxy.get("medical_safety_state"),
            "conflict_state": ku_proxy.get("conflict_state"),
            "freshness_state": ku_proxy.get("freshness_state"),
            "wording": "Governed evidence only; not a diagnosis or prescription.",
        }
        items.append(
            EvidenceBundleItem(
                label=GLOBAL_GOVERNED_KNOWLEDGE_LABEL,
                knowledge_unit_id=ev.knowledge_unit_id,
                content=ev.content,
                evidence_strength=ku_proxy.get("evidence_strength"),
                evidence_type=(ev.metadata or {}).get("knowledge_type") or (ev.metadata or {}).get("evidence_type"),
                freshness_state=ku_proxy.get("freshness_state"),
                publication_state=ku_proxy.get("publication_state"),
                conflict_state=ku_proxy.get("conflict_state"),
                support_direction=support_dir,
                eligibility_state=ev.runtime_eligibility,
                provenance=prov,
                source_attribution=(ev.metadata or {}).get("source_attribution"),
                citation=(ev.metadata or {}).get("citation")
                or f"ku:{ev.knowledge_unit_id}:{ev.immutable_version_id}",
                uncertainty_safety=uncertainty,
                conflict_relation=rel,
                metadata={"retrieval_branch": ev.retrieval_branch, "fusion_rank": ev.fusion_rank},
            )
        )

    return EvidenceBundle(
        query=query,
        intent=intent,
        domain=domain,
        knowledge_plane=GLOBAL_GOVERNED_KNOWLEDGE_LABEL,
        items=items,
        filtered_counts=filtered,
        retrieval_mode=response.mode,
        fallback_state=response.fallback_state.value if hasattr(response.fallback_state, "value") else str(response.fallback_state),
        uncertainty_safety={
            "no_ungrounded_serving": True,
            "pure_vector_only_rag": False,
            "personal_memory_mixed": False,
            "wording": "Uncertainty preserved; conflicting evidence kept labeled separately.",
        },
        request_trace_id=response.request_trace_id,
    )


def evidence_aware_retrieve(
    db: Session,
    *,
    query: str,
    intent: Optional[str] = None,
    domain: Optional[str] = None,
    top_k: int = 8,
    retrieval_mode: RetrievalMode = RetrievalMode.LEXICAL,
    support_labels: Optional[Sequence[LabeledEvidenceRelation]] = None,
) -> EvidenceBundle:
    """
    query → filters/safety/eligibility (via SCIS + hard_exclude) → SCIS substrate → labeled bundle.
    Clinical default = LEXICAL (authorized). HYBRID allowed. VECTOR-only forbidden.
    """
    _forbid_pure_vector(retrieval_mode)
    req = ScisRetrievalRequest(
        query_text=query,
        query_language="en",
        target_domain=domain,
        intent=intent,
        safety_classification="clinical_governed",
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        allowed_knowledge_classes=(GLOBAL_GOVERNED_KNOWLEDGE_LABEL,),
    )
    resp = scis_retrieve(db, req)
    # Enrich metadata from observability/payload already on items where possible.
    for ev in resp.evidence:
        md = dict(ev.metadata or {})
        # Fields may already be sparse; keep label contract.
        md.setdefault("label", GLOBAL_GOVERNED_KNOWLEDGE_LABEL)
        ev.metadata = md
    return build_evidence_bundle_from_scis(
        resp, query=query, intent=intent, domain=domain, support_labels=support_labels
    )
