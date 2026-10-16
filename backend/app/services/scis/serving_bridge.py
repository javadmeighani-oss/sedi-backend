"""Bridge eligible governed KU rows into SCIS KCE.

Lexical/FTS rows are always written. When semantic indexing is enabled
(SEDI_SCIS_SEMANTIC_INDEX_ENABLED, default OFF) the same rows are upgraded in place with
a document vector from the canonical product embedding provider, so one row serves both
the lexical and the vector branch of HYBRID retrieval. Any embedding failure leaves the
lexical row untouched (fail-safe).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility
from backend.app.services.i5.runtime_eligibility_gate import evaluate_knowledge_unit_eligibility
from backend.app.services.scis.lexical_indexing import (
    LEXICAL_ONLY_MODEL_ID,
    index_knowledge_unit_lexical_only,
)

SEMANTIC_INDEX_ENV = "SEDI_SCIS_SEMANTIC_INDEX_ENABLED"
SEMANTIC_BACKFILL_LIMIT_DEFAULT = 200


def semantic_index_enabled() -> bool:
    return os.environ.get(SEMANTIC_INDEX_ENV, "").strip().lower() in {"1", "true", "yes"}


def _semantic_provider(provider: Optional[Any]) -> Optional[Any]:
    if provider is not None:
        return provider
    from backend.app.services.scis.embedding.providers import resolve_product_governed_embedding

    resolved, _mode = resolve_product_governed_embedding(allow_network=True)
    return resolved


def attach_semantic_vectors(
    db: Session,
    rows: Sequence[models.KnowledgeChunkEmbedding],
    *,
    provider: Optional[Any] = None,
) -> int:
    """Upgrade lexical KCE rows in place with document vectors. Returns rows upgraded.

    Only global governed knowledge text is embedded (never user data). Runs in its own
    savepoint: an embedding or DB failure leaves the lexical rows as they were.
    """
    pending = [r for r in rows if r.retracted_at is None and r.model_identifier == LEXICAL_ONLY_MODEL_ID]
    if not pending:
        return 0
    prov = _semantic_provider(provider)
    if prov is None:
        return 0
    from backend.app.services.scis import RESULT_LABEL_GLOBAL
    from backend.app.services.scis.embedding.providers import assert_global_knowledge_only

    chunk_text = {
        int(c.id): str(c.content or "")
        for c in db.query(models.KnowledgeChunk)
        .filter(models.KnowledgeChunk.id.in_([int(r.chunk_id) for r in pending]))
        .all()
    }
    texts = [chunk_text.get(int(r.chunk_id), "") for r in pending]
    savepoint = db.begin_nested()
    try:
        assert_global_knowledge_only(texts, source_class=RESULT_LABEL_GLOBAL)
        vectors = prov.embed_texts(texts, input_type="search_document")
        if len(vectors) != len(pending) or any(len(v) != prov.vector_dimension for v in vectors):
            raise ValueError("SEMANTIC_VECTOR_SHAPE_MISMATCH")
        now = datetime.utcnow()
        for row, vec in zip(pending, vectors):
            db.execute(
                text(
                    """
                    UPDATE knowledge_chunk_embeddings
                    SET embedding_vector = CAST(:v AS vector),
                        model_identifier = :model,
                        vector_dimension = :dim,
                        backend_kind = 'PGVECTOR',
                        embedding_status = 'ready',
                        updated_at = :now
                    WHERE id = :id
                    """
                ),
                {
                    "v": "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]",
                    "model": prov.model_identifier,
                    "dim": int(prov.vector_dimension),
                    "now": now,
                    "id": int(row.id),
                },
            )
            for attr, val in (
                ("embedding_provider", getattr(prov, "provider_name", None)),
                ("embedding_model_version", getattr(prov, "model_version", None)),
            ):
                if hasattr(row, attr):
                    setattr(row, attr, val)
        db.flush()
        savepoint.commit()
    except Exception as exc:  # noqa: BLE001 — keep lexical serving on any failure
        if savepoint.is_active:
            savepoint.rollback()
        print(f"[SCIS] semantic vectors skipped: {type(exc).__name__}: {str(exc)[:200]}")
        return 0
    for row in pending:
        db.refresh(row)
    return len(pending)


def index_eligible_knowledge_unit_if_ready(
    db: Session,
    ku: models.KnowledgeUnit,
    *,
    source_profile_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
    provider: Optional[Any] = None,
) -> List[models.KnowledgeChunkEmbedding]:
    """Index KU into lexical-searchable KCE when runtime eligibility gate passes."""
    gate = evaluate_knowledge_unit_eligibility(ku)
    if gate != KnowledgeUnitRuntimeEligibility.ELIGIBLE:
        return []
    if ku.runtime_eligibility != KnowledgeUnitRuntimeEligibility.ELIGIBLE.value:
        return []
    existing = (
        db.query(models.KnowledgeChunkEmbedding)
        .filter(models.KnowledgeChunkEmbedding.knowledge_unit_id == int(ku.id))
        .all()
    )
    rows = existing or index_knowledge_unit_lexical_only(
        db,
        ku,
        source_profile_id=source_profile_id,
        raw_evidence_id=raw_evidence_id,
    )
    if semantic_index_enabled():
        attach_semantic_vectors(db, rows, provider=provider)
    return list(rows)


def backfill_semantic_vectors(
    db: Session,
    *,
    limit: int = SEMANTIC_BACKFILL_LIMIT_DEFAULT,
    provider: Optional[Any] = None,
) -> int:
    """Bounded backfill of vectors for serving lexical-only rows (no-op unless enabled)."""
    if not semantic_index_enabled():
        return 0
    rows = (
        db.query(models.KnowledgeChunkEmbedding)
        .join(models.KnowledgeUnit, models.KnowledgeUnit.id == models.KnowledgeChunkEmbedding.knowledge_unit_id)
        .filter(models.KnowledgeChunkEmbedding.model_identifier == LEXICAL_ONLY_MODEL_ID)
        .filter(models.KnowledgeChunkEmbedding.retracted_at.is_(None))
        .filter(models.KnowledgeUnit.runtime_eligibility == KnowledgeUnitRuntimeEligibility.ELIGIBLE.value)
        .order_by(models.KnowledgeChunkEmbedding.id)
        .limit(max(0, int(limit)))
        .all()
    )
    return attach_semantic_vectors(db, rows, provider=provider)


__all__ = [
    "SEMANTIC_INDEX_ENV",
    "attach_semantic_vectors",
    "backfill_semantic_vectors",
    "index_eligible_knowledge_unit_if_ready",
    "semantic_index_enabled",
]
