# backend.app.services.local_rag.vector_provider (Stage 17.6, 17.8)
"""
Vector RAG provider. Uses pgvector for similarity search.
Stage 17.8: Daily summaries only.
"""

import os
from typing import List

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.local_rag.contracts import (
    RetrievedChunk,
    RetrievalResult,
    SourceAnchor,
)
from backend.app.services.local_rag.embedding_client import _vector_to_pg_str

RAG_VECTOR_ENABLED = os.environ.get("RAG_VECTOR_ENABLED", "false").lower() in ("true", "1", "yes")
RAG_VECTOR_MODEL = os.environ.get("RAG_VECTOR_MODEL", "text-embedding-3-small")
RAG_VECTOR_TOP_K = int(os.environ.get("RAG_VECTOR_TOP_K", "6") or "6")
RAG_VECTOR_DIM = int(os.environ.get("RAG_VECTOR_DIM", "1536") or "1536")
RAG_VECTOR_MIN_SCORE = float(os.environ.get("RAG_VECTOR_MIN_SCORE", "0.2") or "0.2")
RAG_LOCAL_MAX_CHARS = int(os.environ.get("RAG_LOCAL_MAX_CHARS", "1200") or "1200")


class VectorRAGUnavailableError(Exception):
    """Raised when pgvector or required setup is not available."""

    pass


class VectorRAGProvider:
    """
    Vector RAG provider. Queries rag_embeddings (daily_summary only).
    """

    def __init__(self, db: Session):
        self.db = db

    def retrieve(
        self,
        user_id: int,
        query_text: str,
        language: str = "en",
    ) -> RetrievalResult:
        """
        Retrieve via vector similarity. Daily summaries only.
        """
        self._ensure_pgvector()

        from backend.app.services.local_rag.embedding_client import embed_texts

        query_vec = embed_texts([query_text or "lifestyle summary"])
        if not query_vec:
            raise VectorRAGUnavailableError("Query embedding failed")
        vec_str = _vector_to_pg_str(query_vec[0])

        try:
            rows = self.db.execute(
                text("""
                    SELECT re.id, re.source_id, re.content_hash,
                           1 - (re.embedding <=> :vec::vector) AS score
                    FROM rag_embeddings re
                    WHERE re.user_id = :uid AND re.source_type = 'daily_summary'
                    ORDER BY re.embedding <=> :vec2::vector
                    LIMIT :k
                """),
                {"uid": user_id, "vec": vec_str, "vec2": vec_str, "k": RAG_VECTOR_TOP_K},
            ).fetchall()
        except Exception as e:
            raise VectorRAGUnavailableError(f"pgvector query failed: {e}") from e

        chunks: List[RetrievedChunk] = []
        sources: List[SourceAnchor] = []
        combined_parts: List[str] = []
        budget = RAG_LOCAL_MAX_CHARS

        for row in rows:
            source_id = str(row[1])
            score = float(row[3]) if row[3] is not None else 0
            if score < RAG_VECTOR_MIN_SCORE:
                continue
            try:
                sid = int(source_id)
            except (ValueError, TypeError):
                continue
            dms = (
                self.db.query(models.DailyMemorySummary)
                .filter(models.DailyMemorySummary.id == sid)
                .first()
            )
            if not dms or not dms.summary:
                continue
            text_snippet = dms.summary.strip()[:250]
            label = f"day_{dms.created_at.strftime('%Y-%m-%d')}" if dms.created_at else f"id_{dms.id}"
            ts = dms.created_at.isoformat() if dms.created_at else None
            src: SourceAnchor = {"type": "daily_summary", "id": source_id, "label": label, "ts": ts}
            chunks.append(RetrievedChunk(text_snippet, src))
            if not any(s.get("id") == source_id and s.get("type") == "daily_summary" for s in sources):
                sources.append(src)
            if budget > 0:
                part = text_snippet[:budget]
                combined_parts.append(part)
                budget -= len(part) + 2

        combined_text = "\n\n".join(combined_parts)[:RAG_LOCAL_MAX_CHARS].strip()
        return RetrievalResult(chunks=chunks, combined_text=combined_text, sources=sources)

    def _ensure_pgvector(self) -> None:
        """Verify pgvector extension and rag_embeddings table exist."""
        from sqlalchemy import text

        try:
            r = self.db.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).fetchone()
            if not r:
                raise VectorRAGUnavailableError("pgvector extension not installed")
            self.db.execute(text("SELECT 1 FROM rag_embeddings LIMIT 1"))
        except VectorRAGUnavailableError:
            raise
        except Exception as e:
            raise VectorRAGUnavailableError(f"pgvector/rag_embeddings not ready: {e}") from e
