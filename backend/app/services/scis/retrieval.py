"""SCIS hybrid retrieval entrypoint."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app.services.scis import RESULT_LABEL_GLOBAL
from backend.app.services.scis.contracts import (
    FallbackState,
    RetrievalMode,
    ScisEvidenceItem,
    ScisRetrievalRequest,
    ScisRetrievalResponse,
)
from backend.app.services.scis.eligibility import is_kce_row_eligible
from backend.app.services.scis.embedding.providers import FakeScisEmbeddingProvider, ScisEmbeddingProvider
from backend.app.services.scis.hybrid import RankedCandidate, reciprocal_rank_fusion
from backend.app.services.scis.lexical import lexical_search
from backend.app.services.scis.provenance import build_provenance, provenance_complete_for_accepted
from backend.app.services.scis.vector import vector_search


def _ku_proxy(payload: dict) -> dict:
    return {
        "provenance_complete": payload.get("ku_provenance_complete"),
        "evidence_strength": payload.get("ku_evidence_strength"),
        "freshness_state": payload.get("ku_freshness_state"),
        "conflict_state": payload.get("ku_conflict_state"),
        "medical_safety_state": payload.get("ku_medical_safety_state"),
        "publication_state": payload.get("ku_publication_state"),
        "retraction_reason": payload.get("ku_retraction_reason"),
        "runtime_eligibility": payload.get("ku_runtime_eligibility"),
    }


def _filter_candidates(
    cands: List[RankedCandidate],
    *,
    expected_model: Optional[str],
    filtered_counts: Dict[str, int],
) -> List[RankedCandidate]:
    kept: List[RankedCandidate] = []
    for cand in cands:
        p = cand.payload
        ku = _ku_proxy(p) if p.get("knowledge_unit_id") is not None else None
        decision = is_kce_row_eligible(
            retracted_at=p.get("retracted_at"),
            runtime_eligibility_snapshot=p.get("runtime_eligibility_snapshot"),
            ku=ku,
            expected_embedding_model=expected_model,
            row_model_identifier=p.get("model_identifier"),
            embedding_status=p.get("embedding_status") or "ready",
            backend_kind=p.get("backend_kind"),
        )
        if not decision.allowed:
            filtered_counts[decision.reason] = filtered_counts.get(decision.reason, 0) + 1
            continue
        if not provenance_complete_for_accepted(p):
            filtered_counts["orphan_provenance"] = filtered_counts.get("orphan_provenance", 0) + 1
            continue
        kept.append(cand)
    return kept


def retrieve(db: Session, request: ScisRetrievalRequest, *, provider: Optional[ScisEmbeddingProvider] = None) -> ScisRetrievalResponse:
    trace = request.request_trace_id or str(uuid.uuid4())
    timings: Dict[str, float] = {}
    filtered: Dict[str, int] = {}
    candidates: Dict[str, int] = {}
    fallback = FallbackState.NONE
    error_class: Optional[str] = None
    prov = provider or FakeScisEmbeddingProvider()

    if RESULT_LABEL_GLOBAL not in request.allowed_knowledge_classes:
        return ScisRetrievalResponse(
            request_trace_id=trace,
            mode=request.retrieval_mode.value,
            language=request.query_language,
            evidence=[],
            fallback_state=FallbackState.NO_ELIGIBLE_KNOWLEDGE,
            error_class="KNOWLEDGE_CLASS_DENIED",
        )

    lexical_cands: List[RankedCandidate] = []
    vector_cands: List[RankedCandidate] = []

    if request.retrieval_mode in (RetrievalMode.LEXICAL, RetrievalMode.HYBRID):
        t0 = time.perf_counter()
        lexical_cands, lmeta = lexical_search(
            db,
            request.query_text,
            language=request.query_language,
            top_k=max(request.top_k * 3, 20),
            domain=request.target_domain,
        )
        timings["lexical_ms"] = (time.perf_counter() - t0) * 1000
        if lmeta.get("error"):
            error_class = f"FTS_{lmeta['error']}"
            fallback = FallbackState.FTS_FAILURE
            lexical_cands = []
        candidates["lexical_raw"] = len(lexical_cands)
        lexical_cands = _filter_candidates(lexical_cands, expected_model=None, filtered_counts=filtered)
        candidates["lexical_eligible"] = len(lexical_cands)

    if request.retrieval_mode in (RetrievalMode.VECTOR, RetrievalMode.HYBRID):
        t0 = time.perf_counter()
        try:
            qvec = prov.embed_texts([request.query_text], input_type="search_query")[0]
        except Exception as exc:  # noqa: BLE001
            error_class = type(exc).__name__
            fallback = FallbackState.EMBEDDING_FAILURE
            qvec = None
        if qvec is not None:
            vector_cands, vmeta = vector_search(
                db,
                qvec,
                model_identifier=prov.model_identifier,
                top_k=max(request.top_k * 3, 20),
                domain=request.target_domain,
                expected_dim=prov.vector_dimension,
            )
            if vmeta.get("error"):
                error_class = vmeta["error"]
                fallback = FallbackState.VECTOR_BACKEND_UNAVAILABLE
                vector_cands = []
            candidates["vector_raw"] = len(vector_cands)
            vector_cands = _filter_candidates(
                vector_cands, expected_model=prov.model_identifier, filtered_counts=filtered
            )
            candidates["vector_eligible"] = len(vector_cands)
        timings["vector_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    evidence: List[ScisEvidenceItem] = []
    if request.retrieval_mode == RetrievalMode.LEXICAL:
        ranked = [(c.chunk_id, c.score, {**c.payload, "lexical_rank": c.rank, "branches": ["lexical"]}) for c in lexical_cands]
    elif request.retrieval_mode == RetrievalMode.VECTOR:
        ranked = [(c.chunk_id, c.score, {**c.payload, "vector_rank": c.rank, "branches": ["vector"]}) for c in vector_cands]
    else:
        ranked = reciprocal_rank_fusion([lexical_cands, vector_cands])
        if lexical_cands and not vector_cands:
            fallback = FallbackState.LEXICAL_ONLY if fallback == FallbackState.NONE else fallback
        elif vector_cands and not lexical_cands:
            fallback = FallbackState.VECTOR_ONLY if fallback == FallbackState.NONE else fallback
        elif not lexical_cands and not vector_cands:
            if fallback == FallbackState.NONE:
                fallback = FallbackState.NO_RESULTS
            if error_class in {"FTS_failure",} or fallback in {
                FallbackState.FTS_FAILURE,
                FallbackState.VECTOR_BACKEND_UNAVAILABLE,
                FallbackState.EMBEDDING_FAILURE,
            }:
                if fallback in {FallbackState.FTS_FAILURE, FallbackState.VECTOR_BACKEND_UNAVAILABLE} and (
                    (fallback == FallbackState.FTS_FAILURE and not vector_cands)
                    or (fallback == FallbackState.VECTOR_BACKEND_UNAVAILABLE and not lexical_cands)
                ):
                    pass
                if not lexical_cands and not vector_cands and error_class:
                    if "FTS" in (error_class or "") and "VECTOR" in (error_class or ""):
                        fallback = FallbackState.BOTH_BRANCHES_UNAVAILABLE

    for fusion_rank, (chunk_id, score, payload) in enumerate(ranked[: request.top_k], start=1):
        branches = payload.get("branches") or ["hybrid"]
        branch = "hybrid" if len(branches) > 1 else branches[0]
        content = payload.get("chunk_content") or payload.get("search_document") or ""
        evidence.append(
            ScisEvidenceItem(
                label=RESULT_LABEL_GLOBAL,
                chunk_id=chunk_id,
                content=content,
                language=payload.get("content_language"),
                knowledge_unit_id=payload.get("knowledge_unit_id"),
                immutable_version_id=payload.get("immutable_version_id"),
                retrieval_branch=branch,
                lexical_rank=payload.get("lexical_rank"),
                vector_rank=payload.get("vector_rank"),
                fusion_rank=fusion_rank,
                fusion_score=float(score),
                runtime_eligibility=payload.get("runtime_eligibility_snapshot")
                or payload.get("ku_runtime_eligibility"),
                embedding_model=payload.get("model_identifier"),
                embedding_version=None,
                provenance=build_provenance(payload),
                metadata={
                    "ku_domain": payload.get("ku_domain"),
                    "branches": branches,
                    "ku_provenance_complete": payload.get("ku_provenance_complete"),
                    "ku_evidence_strength": payload.get("ku_evidence_strength"),
                    "ku_freshness_state": payload.get("ku_freshness_state"),
                    "ku_conflict_state": payload.get("ku_conflict_state"),
                    "ku_medical_safety_state": payload.get("ku_medical_safety_state"),
                    "ku_publication_state": payload.get("ku_publication_state"),
                    "ku_retraction_reason": payload.get("ku_retraction_reason"),
                    "retracted_at": payload.get("retracted_at"),
                    "knowledge_type": payload.get("ku_knowledge_type"),
                },
            )
        )
    timings["fusion_ms"] = (time.perf_counter() - t0) * 1000

    if not evidence and fallback == FallbackState.NONE:
        fallback = FallbackState.NO_RESULTS

    return ScisRetrievalResponse(
        request_trace_id=trace,
        mode=request.retrieval_mode.value,
        language=request.query_language,
        evidence=evidence,
        fallback_state=fallback,
        timings_ms=timings,
        candidate_counts=candidates,
        filtered_counts=filtered,
        embedding_model=prov.model_identifier,
        embedding_version=getattr(prov, "model_version", None),
        error_class=error_class,
        observability={
            "safety_classification": request.safety_classification,
            "intent": request.intent,
            "domain": request.target_domain,
            "reranker": "deferred_optional",
        },
    )
