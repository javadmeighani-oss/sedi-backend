# backend.app.services.local_rag.provider_router (Stage 17.6, 17.7, 17.8, 17.9)
"""
Selects RAG provider based on feature flags.
RAG_VECTOR_ENABLED + user in allowlist + circuit breaker not tripped -> vector provider.
Else -> keyword provider.
Stage 17.9: Latency/error guardrails via circuit breaker.
"""

import os
import time
from typing import Union

from sqlalchemy.orm import Session

from backend.app.services.local_rag.contracts import RetrievalResult
from backend.app.services.local_rag.local_provider import LocalRAGProvider
from backend.app.services.local_rag.metrics import get_metrics
from backend.app.services.local_rag.vector_provider import (
    VectorRAGProvider,
    VectorRAGUnavailableError,
    RAG_VECTOR_ENABLED,
)
from backend.app.services.local_rag.circuit_breaker import is_tripped, check_after_request

RAG_VECTOR_ALLOWLIST_RAW = (os.environ.get("RAG_VECTOR_ALLOWLIST", "") or "").strip()
RAG_VECTOR_ALLOWLIST: frozenset[int] = frozenset(
    int(x.strip())
    for x in RAG_VECTOR_ALLOWLIST_RAW.split(",")
    if x.strip() and x.strip().isdigit()
)


def _user_in_allowlist(user_id: int) -> bool:
    return user_id in RAG_VECTOR_ALLOWLIST


def get_rag_provider(db: Session, user_id: int) -> Union[LocalRAGProvider, VectorRAGProvider]:
    """Return the active RAG provider based on flags, allowlist, and circuit breaker."""
    if RAG_VECTOR_ENABLED and _user_in_allowlist(user_id) and not is_tripped():
        return VectorRAGProvider(db)
    return LocalRAGProvider(db)


def retrieve(
    db: Session,
    user_id: int,
    query_text: str,
    language: str = "en",
) -> RetrievalResult:
    """
    Retrieve via provider. If vector enabled and fails, falls back to keyword.
    Records metrics for observability.
    """
    metrics = get_metrics()
    start = time.perf_counter()
    provider = get_rag_provider(db, user_id)
    result = None
    provider_used = "keyword"
    fallback_used = False
    success = False

    try:
        if RAG_VECTOR_ENABLED and isinstance(provider, VectorRAGProvider):
            try:
                result = provider.retrieve(user_id, query_text, language)
                provider_used = "vector"
                success = True
            except VectorRAGUnavailableError:
                result = LocalRAGProvider(db).retrieve(user_id, query_text, language)
                fallback_used = True
                success = True
        else:
            result = provider.retrieve(user_id, query_text, language)
            success = True
    except Exception:
        try:
            result = LocalRAGProvider(db).retrieve(user_id, query_text, language)
            fallback_used = True
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

    # Optional safe log line (no PII)
    print(f"[RAG] provider={provider_used} latency_ms={latency_ms:.1f} sources={sources_count} fallback={fallback_used}")

    return result
