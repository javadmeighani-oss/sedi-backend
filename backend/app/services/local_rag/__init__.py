# backend.app.services.local_rag (Stage 17.5, 17.6 Local RAG v1 + Vector upgrade path)
"""Local RAG layer for Sedi internal stores only."""

from backend.app.services.local_rag.contracts import (
    SourceAnchor,
    RetrievedChunk,
    RetrievalResult,
)
from backend.app.services.local_rag.local_provider import LocalRAGProvider
from backend.app.services.local_rag.provider_router import get_rag_provider, retrieve

__all__ = [
    "SourceAnchor",
    "RetrievedChunk",
    "RetrievalResult",
    "LocalRAGProvider",
    "get_rag_provider",
    "retrieve",
]
