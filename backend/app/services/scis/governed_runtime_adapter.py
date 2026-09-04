"""Minimal SCIS → I5 runtime retrieval adapter (K04).

Deterministic, local, lexical-only. Maps eligible SCIS evidence into
RetrievedKnowledgeItem without KnowledgeMemoryItem dependency.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence

from sqlalchemy.orm import Session

from backend.app.services.i5.runtime_eligibility_gate import evaluate_knowledge_unit_eligibility
from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.runtime_knowledge_retrieval import RetrievedKnowledgeItem
from backend.app.services.scis.contracts import RetrievalMode, ScisRetrievalRequest
from backend.app.services.scis.retrieval import retrieve

# Bounded serving context (chars per evidence statement).
MAX_SERVING_CONTEXT_CHARS = 600
DEFAULT_SERVING_TOP_K = 5


def _lang_matches(item_lang: Optional[str], filter_lang: Optional[str]) -> bool:
    if not filter_lang:
        return True
    fl = filter_lang.strip().lower()
    il = (item_lang or "").strip().lower()
    if not fl:
        return True
    if not il:
        return False
    return il == fl or il.startswith(fl) or fl.startswith(il[:2])


def retrieve_scis_lexical_runtime_items(
    db: Session,
    query: str,
    *,
    language: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = DEFAULT_SERVING_TOP_K,
) -> List[RetrievedKnowledgeItem]:
    """Lexical SCIS retrieve → bounded runtime items (no vector/hybrid)."""
    from backend.app import models

    top_k = max(1, min(int(limit), DEFAULT_SERVING_TOP_K))
    resp = retrieve(
        db,
        ScisRetrievalRequest(
            query_text=query or "",
            query_language=(language or "en"),
            target_domain=domain,
            top_k=top_k,
            retrieval_mode=RetrievalMode.LEXICAL,
        ),
    )

    ku_ids = [e.knowledge_unit_id for e in resp.evidence if e.knowledge_unit_id is not None]
    units: dict[int, Any] = {}
    if ku_ids:
        for ku in db.query(models.KnowledgeUnit).filter(models.KnowledgeUnit.id.in_(ku_ids)).all():
            units[int(ku.id)] = ku

    items: List[RetrievedKnowledgeItem] = []
    seen_canon: set[str] = set()
    for ev in resp.evidence:
        if ev.knowledge_unit_id is None:
            continue
        ku = units.get(int(ev.knowledge_unit_id))
        if ku is None:
            continue
        if not _lang_matches(str(ku.language), language) and not _lang_matches(
            ev.language, language
        ):
            continue
        if domain and str(ku.domain) != domain:
            continue
        if evaluate_knowledge_unit_eligibility(ku) != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
            continue
        if str(ku.runtime_eligibility) != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
            continue
        if not bool(ku.provenance_complete):
            continue
        if getattr(ku, "retraction_reason", None):
            continue
        pub = str(getattr(ku, "publication_state", "") or "")
        if pub in {"SUPERSEDED", "WITHDRAWN"}:
            continue
        if not ev.immutable_version_id:
            continue
        canon = str(ku.canonical_unit_id)
        if canon in seen_canon:
            continue
        seen_canon.add(canon)

        statement = (ev.content or str(ku.normalized_statement) or "").strip()
        if len(statement) > MAX_SERVING_CONTEXT_CHARS:
            statement = statement[: MAX_SERVING_CONTEXT_CHARS - 1].rstrip() + "…"

        prov = ev.provenance
        rank = int(ev.fusion_rank or ev.lexical_rank or (len(items) + 1))
        items.append(
            RetrievedKnowledgeItem(
                knowledge_unit_id=int(ku.id),
                canonical_unit_id=canon,
                immutable_version_id=str(ev.immutable_version_id),
                memory_item_id=f"SCIS_KCE:{int(ev.chunk_id)}",
                memory_row_id=0,
                source_profile_id=getattr(prov, "source_profile_id", None),
                provenance_id=None,
                raw_evidence_id=getattr(prov, "raw_evidence_id", None),
                domain=str(ku.domain),
                language=str(ku.language),
                topic_taxonomy=getattr(ku, "topic_taxonomy", None),
                normalized_statement=statement,
                evidence_strength=str(ku.evidence_strength),
                freshness_state=str(ku.freshness_state),
                conflict_state=str(ku.conflict_state),
                medical_safety_state=str(ku.medical_safety_state),
                runtime_eligibility=str(ku.runtime_eligibility),
                rank_score=max(1, 1000 - rank),
                inclusion_reasons=[
                    "SCIS_LEXICAL",
                    "KU_ELIGIBLE_MATRIX",
                    "PROVENANCE_COMPLETE",
                    f"CHUNK:{int(ev.chunk_id)}",
                    f"BRANCH:{ev.retrieval_branch}",
                ],
            )
        )
        if len(items) >= top_k:
            break
    return items
