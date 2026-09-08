# backend.app.services.local_rag.provider_router (Stage 17.6–17.9 / Phase1 bypass closure)
"""
Product Chat personal lexical router.

Phase1: Stage17 VectorRAGProvider / rag_embeddings@1536 is NONCANONICAL and
unreachable from Product Chat. RAG_VECTOR_ENABLED, allowlist, and circuit breaker
MUST NOT restore Stage17 vector authority.
"""

import os
import time
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.services.local_rag.contracts import RetrievalResult
from backend.app.services.local_rag.local_provider import LocalRAGProvider
from backend.app.services.local_rag.metrics import get_metrics
from backend.app.services.local_rag.circuit_breaker import check_after_request

# Historical flag retained for observability only — cannot select VectorRAG.
RAG_VECTOR_ENABLED = os.environ.get("RAG_VECTOR_ENABLED", "false").lower() in ("true", "1", "yes")
RAG_VECTOR_ALLOWLIST_RAW = (os.environ.get("RAG_VECTOR_ALLOWLIST", "") or "").strip()
RAG_VECTOR_ALLOWLIST: frozenset[int] = frozenset(
    int(x.strip())
    for x in RAG_VECTOR_ALLOWLIST_RAW.split(",")
    if x.strip() and x.strip().isdigit()
)

# Phase1 hard closure: Product Chat never routes to Stage17 vector path.
STAGE17_VECTOR_PRODUCT_CHAT_DISABLED = True
PRODUCT_CHAT_PERSONAL_AUTHORITY_LABEL = "PERSONAL"


def _user_in_allowlist(user_id: int) -> bool:
    return user_id in RAG_VECTOR_ALLOWLIST


def get_rag_provider(db: Session, user_id: int) -> LocalRAGProvider:
    """Always return LocalRAGProvider for Product Chat (Stage17 vector disabled)."""
    _ = (user_id, RAG_VECTOR_ENABLED, _user_in_allowlist(user_id))  # flags observed, ignored
    return LocalRAGProvider(db)


def stage17_vector_reachable_from_product_chat() -> bool:
    """Invariant helper for tests/docs: must remain False in Phase1."""
    return not STAGE17_VECTOR_PRODUCT_CHAT_DISABLED


def retrieve(
    db: Session,
    user_id: int,
    query_text: str,
    language: str = "en",
) -> RetrievalResult:
    """Personal lexical retrieve only. Never queries rag_embeddings."""
    metrics = get_metrics()
    start = time.perf_counter()
    provider_used = "keyword"
    fallback_used = False
    success = False
    result: Optional[RetrievalResult] = None

    try:
        result = LocalRAGProvider(db).retrieve(user_id, query_text, language)
        # Fail-closed PERSONAL boundary: overwrite any upstream authority elevation.
        for src in result.sources or []:
            if isinstance(src, dict):
                src["authority_label"] = PRODUCT_CHAT_PERSONAL_AUTHORITY_LABEL
                src["verified_provider"] = False
                # Strip directory/verification elevation keys if present.
                src.pop("verified_directory", None)
                src.pop("directory_status", None)
                if src.get("doctors_authority_class") not in (None, "PERSONAL_PROVIDER_CONTEXT"):
                    src["doctors_authority_class"] = "PERSONAL_PROVIDER_CONTEXT"
        success = True
    except Exception:
        latency_ms = (time.perf_counter() - start) * 1000
        metrics.record(
            success=False,
            provider_used=provider_used,
            latency_ms=latency_ms,
            top_k=0,
            sources_count=0,
            fallback_used=fallback_used,
        )
        check_after_request(metrics.snapshot())
        raise

    latency_ms = (time.perf_counter() - start) * 1000
    top_k = len(result.chunks) if result else 0
    sources_count = len(result.sources) if result else 0

    metrics.record(
        success=success,
        provider_used=provider_used,
        latency_ms=latency_ms,
        top_k=top_k,
        sources_count=sources_count,
        fallback_used=fallback_used,
    )
    check_after_request(metrics.snapshot())
    print(
        f"[RAG] provider={provider_used} authority=PERSONAL "
        f"latency_ms={latency_ms:.1f} sources={sources_count} "
        f"stage17_vector=disabled"
    )
    return result
