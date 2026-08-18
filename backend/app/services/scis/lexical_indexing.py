"""Lexical-only KCE indexing for I5-S49 (FTS without vector generation)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.scis import CHUNKER_VERSION, RESULT_LABEL_GLOBAL
from backend.app.services.scis.chunking import ChunkDraft, chunk_knowledge_unit
from backend.app.services.scis.embedding.providers import assert_global_knowledge_only
from backend.app.services.scis.indexing import ensure_scis_document
from backend.app.services.scis.normalize import normalize_for_language

LEXICAL_ONLY_MODEL_ID = "scis-lexical-fts-v1"
LEXICAL_ONLY_BACKEND_KIND = "EXTERNAL_VECTOR_DEFERRED"
LEXICAL_ONLY_VECTOR_DIMENSION = 0
LEXICAL_ONLY_EMBEDDING_STATUS = "ready"


def index_chunk_drafts_lexical_only(
    db: Session,
    drafts: Sequence[ChunkDraft],
    *,
    document: models.KnowledgeDocument,
    runtime_eligibility: str = "ELIGIBLE",
    source_profile_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
) -> List[models.KnowledgeChunkEmbedding]:
    texts = [d.text for d in drafts]
    assert_global_knowledge_only(texts, source_class=RESULT_LABEL_GLOBAL)

    out: List[models.KnowledgeChunkEmbedding] = []
    now = datetime.utcnow()
    for draft in drafts:
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
                    "index_mode": "LEXICAL_FTS_ONLY",
                }
            ),
        )
        db.add(chunk)
        db.flush()

        search_doc = normalize_for_language(draft.text, draft.language)
        row = models.KnowledgeChunkEmbedding(
            chunk_id=chunk.id,
            model_identifier=LEXICAL_ONLY_MODEL_ID,
            vector_dimension=LEXICAL_ONLY_VECTOR_DIMENSION,
            content_hash=draft.chunk_hash,
            embedding_status=LEXICAL_ONLY_EMBEDDING_STATUS,
            embedding_json=None,
            version=1,
            generated_at=now,
            created_at=now,
            updated_at=now,
            knowledge_unit_id=draft.knowledge_unit_id,
            immutable_version_id=draft.immutable_version_id,
            source_profile_id=source_profile_id,
            raw_evidence_id=raw_evidence_id,
            index_generation=1,
            backend_kind=LEXICAL_ONLY_BACKEND_KIND,
            runtime_eligibility_snapshot=runtime_eligibility,
            retracted_at=None,
        )
        for attr, val in (
            ("embedding_provider", None),
            ("embedding_model_version", None),
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

        db.execute(
            text(
                """
                UPDATE knowledge_chunk_embeddings
                SET search_tsv = to_tsvector('simple', COALESCE(:sd, ''))
                WHERE id = :id
                """
            ),
            {"sd": search_doc, "id": row.id},
        )
        out.append(row)
    db.commit()
    for r in out:
        db.refresh(r)
    return out


def index_knowledge_unit_lexical_only(
    db: Session,
    ku: models.KnowledgeUnit,
    *,
    source_profile_id: Optional[int] = None,
    raw_evidence_id: Optional[int] = None,
) -> List[models.KnowledgeChunkEmbedding]:
    drafts = chunk_knowledge_unit(ku)
    doc = ensure_scis_document(db, title=f"SCIS KU {ku.canonical_unit_id}")
    return index_chunk_drafts_lexical_only(
        db,
        drafts,
        document=doc,
        runtime_eligibility=ku.runtime_eligibility,
        source_profile_id=source_profile_id,
        raw_evidence_id=raw_evidence_id,
    )
