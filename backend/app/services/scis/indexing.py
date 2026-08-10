"""Index/write pipeline: chunk → embed → KCE (pgvector + FTS)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.scis import CHUNKER_VERSION, DEFAULT_EMBEDDING_DIM, RESULT_LABEL_GLOBAL
from backend.app.services.scis.chunking import ChunkDraft, chunk_knowledge_unit
from backend.app.services.scis.embedding.providers import (
    FakeScisEmbeddingProvider,
    ScisEmbeddingProvider,
    assert_global_knowledge_only,
)
from backend.app.services.scis.normalize import normalize_for_language


def _vector_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def ensure_scis_document(db: Session, *, title: str = "SCIS-01 Fixture Document") -> models.KnowledgeDocument:
    src = (
        db.query(models.KnowledgeSource)
        .filter(models.KnowledgeSource.slug == "scis-01-synthetic-governed")
        .first()
    )
    if src is None:
        src = models.KnowledgeSource(
            slug="scis-01-synthetic-governed",
            name="SCIS-01 Synthetic Governed Source",
            category="health_education",
            trust_level="editorial",
            locale="en",
            ingestion_status="approved",
            source_fetch_enabled=False,
            fetch_method="manual_upload",
            review_required=True,
        )
        db.add(src)
        db.flush()
    doc = (
        db.query(models.KnowledgeDocument)
        .filter(
            models.KnowledgeDocument.source_id == src.id,
            models.KnowledgeDocument.title == title,
        )
        .first()
    )
    if doc is None:
        doc = models.KnowledgeDocument(
            source_id=src.id,
            title=title,
            status="published",
            locale="en",
            category="health_education",
            published_at=datetime.utcnow(),
        )
        db.add(doc)
        db.flush()
    return doc


def index_chunk_drafts(
    db: Session,
    drafts: Sequence[ChunkDraft],
    *,
    document: models.KnowledgeDocument,
    provider: Optional[ScisEmbeddingProvider] = None,
    runtime_eligibility: str = "ELIGIBLE",
    source_profile_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
) -> List[models.KnowledgeChunkEmbedding]:
    prov = provider or FakeScisEmbeddingProvider()
    texts = [d.text for d in drafts]
    assert_global_knowledge_only(texts, source_class=RESULT_LABEL_GLOBAL)
    vectors = prov.embed_texts(texts, input_type="search_document")
    if any(len(v) != prov.vector_dimension for v in vectors):
        raise ValueError("VECTOR_DIMENSION_MISMATCH")
    if prov.vector_dimension != DEFAULT_EMBEDDING_DIM:
        raise ValueError("UNSUPPORTED_EMBEDDING_DIMENSION")

    out: List[models.KnowledgeChunkEmbedding] = []
    now = datetime.utcnow()
    for draft, vec in zip(drafts, vectors):
        chunk = models.KnowledgeChunk(
            document_id=document.id,
            chunk_index=draft.chunk_index,
            content=draft.text,
            citation_label=f"scis:{draft.chunk_identity[:12]}",
            token_count=len(draft.text.split()),
            metadata_json=json.dumps(
                {
                    "chunk_identity": draft.chunk_identity,
                    "chunk_hash": draft.chunk_hash,
                    "section_path": draft.section_path,
                    "chunker_version": draft.chunker_version,
                    "label": RESULT_LABEL_GLOBAL,
                }
            ),
        )
        db.add(chunk)
        db.flush()

        search_doc = normalize_for_language(draft.text, draft.language)
        row = models.KnowledgeChunkEmbedding(
            chunk_id=chunk.id,
            model_identifier=prov.model_identifier,
            vector_dimension=prov.vector_dimension,
            content_hash=draft.chunk_hash,
            embedding_status="ready",
            embedding_json=json.dumps(vec),
            version=1,
            generated_at=now,
            created_at=now,
            updated_at=now,
            knowledge_unit_id=draft.knowledge_unit_id,
            immutable_version_id=draft.immutable_version_id,
            source_profile_id=source_profile_id,
            raw_evidence_id=raw_evidence_id,
            index_generation=1,
            backend_kind="PGVECTOR",
            runtime_eligibility_snapshot=runtime_eligibility,
            retracted_at=None,
        )
        # Extended SCIS-01 columns (may exist after migration 061)
        for attr, val in (
            ("embedding_provider", getattr(prov, "provider_name", "fake")),
            ("embedding_model_version", getattr(prov, "model_version", "v1")),
            ("chunker_version", CHUNKER_VERSION),
            ("chunk_version", 1),
            ("section_path", draft.section_path),
            ("content_language", draft.language),
            ("search_document", search_doc),
        ):
            if hasattr(models.KnowledgeChunkEmbedding, attr):
                setattr(row, attr, val)
        db.add(row)
        db.flush()

        # Set pgvector + tsvector via SQL for type safety
        db.execute(
            text(
                """
                UPDATE knowledge_chunk_embeddings
                SET embedding_vector = CAST(:v AS vector),
                    search_tsv = to_tsvector('simple', COALESCE(:sd, ''))
                WHERE id = :id
                """
            ),
            {"v": _vector_literal(vec), "sd": search_doc, "id": row.id},
        )
        out.append(row)
    db.commit()
    for r in out:
        db.refresh(r)
    return out


def index_knowledge_unit(
    db: Session,
    ku: models.KnowledgeUnit,
    *,
    provider: Optional[ScisEmbeddingProvider] = None,
    source_profile_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
) -> List[models.KnowledgeChunkEmbedding]:
    drafts = chunk_knowledge_unit(ku)
    doc = ensure_scis_document(db, title=f"SCIS KU {ku.canonical_unit_id}")
    return index_chunk_drafts(
        db,
        drafts,
        document=doc,
        provider=provider,
        runtime_eligibility=ku.runtime_eligibility,
        source_profile_id=source_profile_id,
        raw_evidence_id=raw_evidence_id,
    )
