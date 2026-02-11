# backend.app.services.local_rag.embedding_client (Stage 17.8)
"""
OpenAI embeddings client. No text logging. Batched requests.
"""

import os
from typing import List

EMBED_BATCH_SIZE = 16
EMBED_TIMEOUT = 30.0
RAG_VECTOR_MODEL = os.environ.get("RAG_VECTOR_MODEL", "text-embedding-3-small")


def _get_client():
    """Lazy init to avoid import-time failures when OPENAI_API_KEY not set."""
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set; embeddings unavailable")
    return OpenAI(api_key=api_key)


def _vector_to_pg_str(vec: List[float]) -> str:
    """Format vector for pgvector INSERT (no pgvector package needed)."""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed texts via OpenAI. Batches of 16, timeout 30s.
    Never logs text. Returns empty list on failure.
    """
    if not texts:
        return []
    results: List[List[float]] = []
    client = _get_client()
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        batch = [t if t and isinstance(t, str) else "" for t in batch]
        try:
            r = client.embeddings.create(
                input=batch,
                model=RAG_VECTOR_MODEL,
                timeout=EMBED_TIMEOUT,
            )
            for d in sorted(r.data, key=lambda x: x.index):
                emb = d.embedding
                results.append(list(emb) if not isinstance(emb, list) else emb)
        except Exception:
            raise
    return results
