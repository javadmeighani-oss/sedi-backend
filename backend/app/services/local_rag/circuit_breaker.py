# backend.app.services.local_rag.circuit_breaker (Stage 17.9)
"""
Global circuit breaker for vector RAG. Process-local. Resets on restart.
"""

import os
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

RAG_VECTOR_P95_MAX_MS = float(os.environ.get("RAG_VECTOR_P95_MAX_MS", "500") or "500")
RAG_VECTOR_ERROR_MAX = int(os.environ.get("RAG_VECTOR_ERROR_MAX", "5") or "5")
RAG_VECTOR_FALLBACK_TTL_SECONDS = int(os.environ.get("RAG_VECTOR_FALLBACK_TTL_SECONDS", "600") or "600")

_tripped_until: Optional[datetime] = None
_last_reason: Optional[str] = None
_lock = threading.Lock()


def is_tripped() -> bool:
    """True if breaker is currently tripped (use keyword)."""
    with _lock:
        if _tripped_until is None:
            return False
        if datetime.utcnow() >= _tripped_until:
            return False
        return True


def _trip(reason: str) -> None:
    with _lock:
        global _tripped_until, _last_reason
        _tripped_until = datetime.utcnow() + timedelta(seconds=RAG_VECTOR_FALLBACK_TTL_SECONDS)
        _last_reason = reason


def check_after_request(snapshot: Dict[str, Any]) -> None:
    """
    After a request, check metrics. Trip if p95 > threshold or errors_in_last_50 > threshold.
    """
    p95 = snapshot.get("latency", {}).get("p95_ms") or 0
    errors_last_50 = snapshot.get("errors_in_last_50", 0)

    if p95 > RAG_VECTOR_P95_MAX_MS:
        _trip(f"p95_latency={p95}ms > {RAG_VECTOR_P95_MAX_MS}ms")
    elif errors_last_50 > RAG_VECTOR_ERROR_MAX:
        _trip(f"errors_in_last_50={errors_last_50} > {RAG_VECTOR_ERROR_MAX}")


def get_state() -> Dict[str, Any]:
    """Return breaker state for admin endpoint."""
    with _lock:
        now = datetime.utcnow()
        tripped = _tripped_until is not None and now < _tripped_until
        return {
            "is_tripped": tripped,
            "tripped_until": _tripped_until.isoformat() if _tripped_until else None,
            "last_reason": _last_reason,
            "thresholds": {
                "p95_max_ms": RAG_VECTOR_P95_MAX_MS,
                "error_max": RAG_VECTOR_ERROR_MAX,
                "fallback_ttl_seconds": RAG_VECTOR_FALLBACK_TTL_SECONDS,
            },
        }
