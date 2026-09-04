"""PostgreSQL FTS lexical retrieval for SCIS."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.services.scis.hybrid import RankedCandidate
from backend.app.services.scis.lexical_query import (
    LexicalQueryPlan,
    formulate_lexical_query_plan,
    token_coverage_score,
)
from backend.app.services.scis.normalize import normalize_for_language


def build_search_document(*, content: str, language: str | None) -> str:
    return normalize_for_language(content, language)


_FTS_SQL = text(
    """
    SELECT
      kce.id AS kce_id,
      kce.chunk_id AS chunk_id,
      kce.knowledge_unit_id AS knowledge_unit_id,
      kce.immutable_version_id AS immutable_version_id,
      kce.raw_evidence_id AS raw_evidence_id,
      kce.source_profile_id AS source_profile_id,
      kce.runtime_eligibility_snapshot AS runtime_eligibility_snapshot,
      kce.retracted_at AS retracted_at,
      kce.model_identifier AS model_identifier,
      kce.embedding_status AS embedding_status,
      kce.backend_kind AS backend_kind,
      kce.content_language AS content_language,
      kce.search_document AS search_document,
      kc.content AS chunk_content,
      ku.domain AS ku_domain,
      ku.runtime_eligibility AS ku_runtime_eligibility,
      ku.provenance_complete AS ku_provenance_complete,
      ku.evidence_strength AS ku_evidence_strength,
      ku.freshness_state AS ku_freshness_state,
      ku.conflict_state AS ku_conflict_state,
      ku.medical_safety_state AS ku_medical_safety_state,
      ku.publication_state AS ku_publication_state,
      ku.retraction_reason AS ku_retraction_reason,
      ts_rank_cd(kce.search_tsv, plainto_tsquery('simple', :q)) AS rank_score
    FROM knowledge_chunk_embeddings kce
    JOIN knowledge_chunks kc ON kc.id = kce.chunk_id
    LEFT JOIN knowledge_units ku ON ku.id = kce.knowledge_unit_id
    WHERE kce.search_tsv @@ plainto_tsquery('simple', :q)
      AND kce.retracted_at IS NULL
      AND (:domain IS NULL OR ku.domain = :domain)
    ORDER BY rank_score DESC, kce.chunk_id ASC
    LIMIT :lim
    """
)


def _execute_fts(
    db: Session,
    *,
    q: str,
    domain: Optional[str],
    lim: int,
) -> Tuple[List[Any], Optional[str]]:
    if not q:
        return [], None
    try:
        rows = db.execute(_FTS_SQL, {"q": q, "domain": domain, "lim": lim}).mappings().all()
        return list(rows), None
    except Exception as exc:  # noqa: BLE001 — surface as FTS failure
        return [], type(exc).__name__


def _rows_to_candidates(
    rows: Sequence[Any],
    *,
    coverage_tokens: Sequence[str],
    top_k: int,
) -> List[RankedCandidate]:
    scored: List[Tuple[float, float, int, Any]] = []
    for row in rows:
        rank_score = float(row["rank_score"] or 0.0)
        hay = f"{row.get('search_document') or ''} {row.get('chunk_content') or ''}"
        coverage = token_coverage_score(hay, coverage_tokens)
        scored.append((rank_score, coverage, int(row["chunk_id"]), row))
    # Prefer FTS rank, then query-token coverage (demotes incidental acronym hits).
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    cands: List[RankedCandidate] = []
    for i, (rank_score, coverage, _cid, row) in enumerate(scored[:top_k], start=1):
        payload = dict(row)
        payload["query_token_coverage"] = coverage
        cands.append(
            RankedCandidate(
                chunk_id=int(row["chunk_id"]),
                branch="lexical",
                rank=i,
                score=float(rank_score),
                payload=payload,
            )
        )
    return cands


def lexical_search(
    db: Session,
    query: str,
    *,
    language: str = "en",
    top_k: int = 20,
    domain: Optional[str] = None,
) -> Tuple[List[RankedCandidate], Dict[str, Any]]:
    """FTS over knowledge_chunk_embeddings.search_tsv (simple config).

    Uses plainto_tsquery on a deterministic QueryPlan (PRIMARY, optional FALLBACK)
    so natural-language function words are not AND-required. FA/AR rely on
    normalization, not language-specific stemming dictionaries.
    """
    plan: LexicalQueryPlan = formulate_lexical_query_plan(query, language=language)
    meta: Dict[str, Any] = {
        "branch": "lexical",
        "config": "simple",
        "error": None,
        "query_plan": {
            "original_query": plan.original_query,
            "normalized_original": plan.normalized_original,
            "primary_query": plan.primary_query,
            "fallback_query": plan.fallback_query,
            "original_token_count": plan.original_token_count,
            "primary_token_count": plan.primary_token_count,
            "fallback_token_count": plan.fallback_token_count,
            "used": None,
        },
    }
    if not plan.primary_query and not plan.fallback_query:
        return [], meta

    fetch_lim = max(top_k * 3, 20)
    coverage_tokens = plan.primary_tokens or plan.fallback_tokens

    rows, err = _execute_fts(db, q=plan.primary_query, domain=domain, lim=fetch_lim)
    used = "primary"
    if err:
        meta["error"] = err
        return [], meta

    if not rows and plan.fallback_query:
        rows, err = _execute_fts(db, q=plan.fallback_query, domain=domain, lim=fetch_lim)
        used = "fallback"
        if err:
            meta["error"] = err
            return [], meta

    meta["query_plan"]["used"] = used if rows or used == "primary" else used
    cands = _rows_to_candidates(rows, coverage_tokens=coverage_tokens, top_k=top_k)
    meta["raw_count"] = len(cands)
    return cands, meta
