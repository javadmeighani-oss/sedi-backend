"""pgvector candidate retrieval for SCIS."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.services.scis import DEFAULT_EMBEDDING_DIM
from backend.app.services.scis.hybrid import RankedCandidate


def _vector_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def vector_search(
    db: Session,
    query_vector: Sequence[float],
    *,
    model_identifier: str,
    top_k: int = 20,
    domain: Optional[str] = None,
    expected_dim: int = DEFAULT_EMBEDDING_DIM,
) -> Tuple[List[RankedCandidate], Dict[str, Any]]:
    meta: Dict[str, Any] = {"branch": "vector", "error": None}
    if len(query_vector) != expected_dim:
        meta["error"] = "VECTOR_DIMENSION_MISMATCH"
        return [], meta

    vlit = _vector_literal(query_vector)
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
          (kce.embedding_vector <=> CAST(:qvec AS vector)) AS dist
        FROM knowledge_chunk_embeddings kce
        JOIN knowledge_chunks kc ON kc.id = kce.chunk_id
        LEFT JOIN knowledge_units ku ON ku.id = kce.knowledge_unit_id
        WHERE kce.embedding_vector IS NOT NULL
          AND kce.embedding_status = 'ready'
          AND kce.model_identifier = :model
          AND kce.retracted_at IS NULL
          AND kce.backend_kind = 'PGVECTOR'
          AND (:domain IS NULL OR ku.domain = :domain)
        ORDER BY dist ASC, kce.chunk_id ASC
        LIMIT :lim
        """
    )
    try:
        rows = db.execute(
            sql, {"qvec": vlit, "model": model_identifier, "domain": domain, "lim": top_k}
        ).mappings().all()
    except Exception as exc:  # noqa: BLE001
        meta["error"] = type(exc).__name__
        return [], meta

    cands: List[RankedCandidate] = []
    for i, row in enumerate(rows, start=1):
        dist = float(row["dist"] or 0.0)
        score = 1.0 / (1.0 + dist)
        cands.append(
            RankedCandidate(
                chunk_id=int(row["chunk_id"]),
                branch="vector",
                rank=i,
                score=score,
                payload=dict(row),
            )
        )
    meta["raw_count"] = len(cands)
    return cands, meta
