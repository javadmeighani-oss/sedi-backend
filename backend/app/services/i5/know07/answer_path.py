"""KNOW-07 → W4-P02 grounded answer path (global governed knowledge only).

Reuses existing SCIS evidence-aware retrieval + reference_renderer.
No parallel public API. No I6/I7 personal-memory plane.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.services.i5.know07 import GLOBAL_GOVERNED_KNOWLEDGE_LABEL
from backend.app.services.i5.know07.conflict import label_evidence_relation
from backend.app.services.i5.know07.evidence_bundle import EvidenceBundle, evidence_aware_retrieve
from backend.app.services.i5.know07.exclusions import hard_exclude_ku
from backend.app.services.i5.reference_renderer import (
    STATUS_OK,
    render_grounded_answer,
)
from backend.app.services.scis.contracts import RetrievalMode


@dataclass(frozen=True)
class ProductionAnswerTrace:
    query: str
    intent: Optional[str]
    evidence_count: int
    retrieved_ku_ids: list[int]
    source_ids: list[int]
    provenance: bool
    current_version_only: bool
    evidence_bundle: bool
    synthesis_grounded: bool
    citation_or_attribution: bool
    safety_uncertainty: bool
    knowledge_plane: str
    synthesized_text: str
    status: str
    support_directions: list[str]
    filtered_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "evidence_count": self.evidence_count,
            "retrieved_ku_ids": self.retrieved_ku_ids,
            "source_ids": self.source_ids,
            "provenance": self.provenance,
            "current_version_only": self.current_version_only,
            "evidence_bundle": self.evidence_bundle,
            "synthesis_grounded": self.synthesis_grounded,
            "citation_or_attribution": self.citation_or_attribution,
            "safety_uncertainty": self.safety_uncertainty,
            "knowledge_plane": self.knowledge_plane,
            "synthesized_text": self.synthesized_text[:500],
            "status": self.status,
            "support_directions": self.support_directions,
            "filtered_counts": dict(self.filtered_counts),
        }


def bundle_to_retrieval_payload(bundle: EvidenceBundle) -> dict[str, Any]:
    """Adapt KNOW-07 evidence bundle into W4-P02 retrieval shape."""
    items: List[Dict[str, Any]] = []
    for it in bundle.items:
        prov = it.provenance or {}
        items.append(
            {
                "knowledge_unit_id": it.knowledge_unit_id,
                "canonical_unit_id": f"ku-{it.knowledge_unit_id}",
                "immutable_version_id": prov.get("immutable_version_id") or "v1",
                "normalized_statement": it.content,
                "content": it.content,
                "evidence_strength": it.evidence_strength or "UNKNOWN",
                "freshness_state": it.freshness_state or "CURRENT",
                "conflict_state": it.conflict_state or "NONE",
                "medical_safety_state": (it.uncertainty_safety or {}).get("medical_safety_state")
                or "CLEARED",
                "provenance_id": None,
                "source_profile_id": prov.get("source_profile_id"),
                "raw_evidence_id": prov.get("raw_evidence_id"),
                "citation": {"label": it.citation or f"KU:{it.knowledge_unit_id}"},
                "support_direction": it.support_direction,
            }
        )
    return {
        "status": "OK" if items else "NO_ELIGIBLE_KNOWLEDGE",
        "query_id": bundle.query,
        "trace_id": bundle.request_trace_id,
        "items": items,
        "exclusions": [
            {"reason": code, "count": n} for code, n in (bundle.filtered_counts or {}).items()
        ],
        "knowledge_plane": bundle.knowledge_plane,
    }


def produce_grounded_answer(
    db: Session,
    *,
    query: str,
    intent: Optional[str] = "clinical",
    domain: Optional[str] = None,
    top_k: int = 5,
) -> ProductionAnswerTrace:
    """Authorized production answer path: SCIS lexical → evidence bundle → W4-P02 synthesis."""
    bundle = evidence_aware_retrieve(
        db,
        query=query,
        intent=intent,
        domain=domain,
        top_k=top_k,
        retrieval_mode=RetrievalMode.LEXICAL,
        support_labels=[label_evidence_relation(support_direction="SUPPORTS")],
    )
    assert bundle.knowledge_plane == GLOBAL_GOVERNED_KNOWLEDGE_LABEL
    payload = bundle_to_retrieval_payload(bundle)
    answer = render_grounded_answer(payload, user_requested_sources=True)

    ku_ids = [int(i.knowledge_unit_id) for i in bundle.items if i.knowledge_unit_id is not None]
    source_ids = sorted(
        {
            int(i.provenance["source_profile_id"])
            for i in bundle.items
            if (i.provenance or {}).get("source_profile_id") is not None
        }
    )
    current_only = all(
        (i.freshness_state in (None, "CURRENT"))
        and (i.publication_state in (None, "PUBLISHED", "CURRENT") or True)
        for i in bundle.items
    )
    # Tighten current-version: reject STALE/SUPERSEDED if present in metadata.
    for i in bundle.items:
        if i.freshness_state in {"STALE", "EXPIRED"}:
            current_only = False
        if i.publication_state in {"SUPERSEDED", "WITHDRAWN"}:
            current_only = False

    provenance_ok = all(bool(i.provenance) for i in bundle.items) if bundle.items else True
    citation_ok = all(bool(i.citation or i.source_attribution) for i in bundle.items) if bundle.items else True
    safety_ok = bool(bundle.uncertainty_safety) and (
        all(bool(i.uncertainty_safety) for i in bundle.items) if bundle.items else True
    )
    if bundle.items:
        grounded = bool(answer.synthesized_text) and answer.no_base_model_fallback is True
    else:
        # Fail-closed empty path: no base-model medical fallback.
        grounded = answer.no_base_model_fallback is True

    dirs = [d for d in (i.support_direction for i in bundle.items) if d]
    return ProductionAnswerTrace(
        query=query,
        intent=intent,
        evidence_count=len(bundle.items),
        retrieved_ku_ids=ku_ids,
        source_ids=source_ids,
        provenance=provenance_ok if bundle.items else True,
        current_version_only=current_only if bundle.items else True,
        evidence_bundle=True,
        synthesis_grounded=bool(grounded),
        citation_or_attribution=citation_ok if bundle.items else True,
        safety_uncertainty=safety_ok,
        knowledge_plane=bundle.knowledge_plane,
        synthesized_text=answer.synthesized_text or "",
        status=answer.status,
        support_directions=dirs,
        filtered_counts=dict(bundle.filtered_counts or {}),
    )


def assert_ungrounded_blocked(ku_like: dict) -> str:
    """Return exclusion code; raises if somehow allowed."""
    d = hard_exclude_ku(ku_like)
    if not d.excluded:
        raise ValueError("UNGROUNDED_EVIDENCE_NOT_BLOCKED")
    return d.code
