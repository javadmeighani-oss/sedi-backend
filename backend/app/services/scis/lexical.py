"""PostgreSQL FTS lexical retrieval for SCIS."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.services.scis.hybrid import RankedCandidate
from backend.app.services.scis.normalize import normalize_for_language


def build_search_document(*, content: str, language: str | None) -> str:
    return normalize_for_language(content, language)


def lexical_search(
    db: Session,
    query: str,
    *,
    language: str = "en",
    top_k: int = 20,
    domain: Optional[str] = None,
) -> Tuple[List[RankedCandidate], Dict[str, Any]]:
    """FTS over knowledge_chunk_embeddings.search_tsv (simple config).

    Uses plainto_tsquery on normalized query. FA/AR rely on normalization,
    not language-specific stemming dictionaries.
    """
    meta: Dict[str, Any] = {"branch": "lexical", "config": "simple", "error": None}
    qnorm = normalize_for_language(query, language)
    if not qnorm:
        return [], meta

    sql = text(
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
    try:
        rows = db.execute(sql, {"q": qnorm, "domain": domain, "lim": top_k}).mappings().all()
    except Exception as exc:  # noqa: BLE001 — surface as FTS failure
        meta["error"] = type(exc).__name__
        return [], meta

    cands: List[RankedCandidate] = []
    for i, row in enumerate(rows, start=1):
        cands.append(
            RankedCandidate(
                chunk_id=int(row["chunk_id"]),
                branch="lexical",
                rank=i,
                score=float(row["rank_score"] or 0.0),
                payload=dict(row),
            )
        )
    meta["raw_count"] = len(cands)
    return cands, meta
