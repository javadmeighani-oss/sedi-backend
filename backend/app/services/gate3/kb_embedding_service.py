"""KB embedding foundation — provider-neutral, no pgvector required."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import List, Optional, Protocol

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags

DEFAULT_MODEL = "fake-embedding-v1"
DEFAULT_DIM = 8


class EmbeddingProvider(Protocol):
    model_identifier: str
    vector_dimension: int

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        ...


class FakeEmbeddingProvider:
    """Deterministic fake embeddings for tests — no external API calls."""

    model_identifier = DEFAULT_MODEL
    vector_dimension = DEFAULT_DIM

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [round(digest[i % len(digest)] / 255.0, 6) for i in range(self.vector_dimension)]
            out.append(vec)
        return out


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def upsert_chunk_embedding(
    db: Session,
    chunk: models.KnowledgeChunk,
    provider: Optional[EmbeddingProvider] = None,
) -> Optional[models.KnowledgeChunkEmbedding]:
    if not feature_flags.kb_embeddings_enabled():
        return None

    prov = provider or FakeEmbeddingProvider()
    chash = content_hash(chunk.content)
    existing = (
        db.query(models.KnowledgeChunkEmbedding)
        .filter(
            models.KnowledgeChunkEmbedding.chunk_id == chunk.id,
            models.KnowledgeChunkEmbedding.model_identifier == prov.model_identifier,
        )
        .first()
    )
    if existing and existing.content_hash == chash and existing.embedding_status == "ready":
        return existing

    vectors = prov.embed_texts([chunk.content])
    now = datetime.utcnow()
    if existing:
        existing.content_hash = chash
        existing.embedding_json = json.dumps(vectors[0])
        existing.embedding_status = "ready"
        existing.generated_at = now
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        return existing

    row = models.KnowledgeChunkEmbedding(
        chunk_id=chunk.id,
        model_identifier=prov.model_identifier,
        vector_dimension=prov.vector_dimension,
        content_hash=chash,
        embedding_status="ready",
        embedding_json=json.dumps(vectors[0]),
        generated_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
