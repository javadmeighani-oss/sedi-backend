# backend.app.services.local_rag.contracts (Stage 17.5)
"""
RAG contract types. SourceAnchor matches Lifestyle sources format (Stage 17.3).
"""

from typing import List, Dict, Any, Optional


# Source anchor: type, id, label, ts? (matches lifestyle summary sources)
SourceAnchor = Dict[str, Any]


class RetrievedChunk:
    """A single retrieved text chunk with its source anchor."""

    def __init__(self, text: str, source: SourceAnchor):
        self.text = text
        self.source = source


class RetrievalResult:
    """Result of local RAG retrieval."""

    def __init__(
        self,
        chunks: List[RetrievedChunk],
        combined_text: str,
        sources: List[SourceAnchor],
    ):
        self.chunks = chunks
        self.combined_text = combined_text
        self.sources = sources
