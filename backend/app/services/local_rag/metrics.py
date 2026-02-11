# backend.app.services.local_rag.metrics (Stage 17.7)
"""
In-memory RAG metrics collector. Thread-safe. Resets on restart.
"""

import threading
from collections import deque
from datetime import datetime
from typing import Dict, Any

LATENCY_BUCKETS = [50, 100, 200, 500, 1000]
LAST_N_LATENCIES = 50
LAST_N_FOR_ERRORS = 50


def _init_buckets() -> Dict[str, int]:
    d = {f"<{b}": 0 for b in LATENCY_BUCKETS}
    d[">=1000"] = 0
    return d


class RAGMetricsCollector:
    """Thread-safe in-memory metrics for RAG retrieval."""

    _lock = threading.Lock()

    def __init__(self):
        self.total_requests = 0
        self.provider_vector_used = 0
        self.provider_keyword_used = 0
        self.vector_fallbacks = 0
        self.errors = 0
        self._latency_sum = 0.0
        self._latency_count = 0
        self._last_latencies: deque = deque(maxlen=LAST_N_LATENCIES)
        self._recent_errors: deque = deque(maxlen=LAST_N_FOR_ERRORS)
        self._bucket_counts = _init_buckets()
        self._last_updated_at: datetime | None = None

    def record(
        self,
        success: bool,
        provider_used: str,
        latency_ms: float,
        top_k: int,
        sources_count: int,
        fallback_used: bool = False,
    ) -> None:
        """Record a retrieval attempt."""
        with self._lock:
            self.total_requests += 1
            if provider_used == "vector":
                self.provider_vector_used += 1
            else:
                self.provider_keyword_used += 1
            if fallback_used:
                self.vector_fallbacks += 1
            if not success:
                self.errors += 1
            self._recent_errors.append(not success)

            if latency_ms >= 0:
                self._latency_sum += latency_ms
                self._latency_count += 1
                self._last_latencies.append(latency_ms)

                for b in LATENCY_BUCKETS:
                    if latency_ms < b:
                        self._bucket_counts[f"<{b}"] = self._bucket_counts.get(f"<{b}", 0) + 1
                        break
                else:
                    self._bucket_counts[">=1000"] = self._bucket_counts.get(">=1000", 0) + 1

            self._last_updated_at = datetime.utcnow()

    def snapshot(self) -> Dict[str, Any]:
        """Return current metrics snapshot (for admin endpoint)."""
        with self._lock:
            avg_ms = self._latency_sum / self._latency_count if self._latency_count else 0
            latencies = sorted(self._last_latencies)
            n = len(latencies)
            p50 = latencies[n // 2] if n else 0
            p95_idx = max(1, int(n * 0.95)) if n else 0
            p95 = latencies[p95_idx - 1] if n and p95_idx > 0 else 0

            buckets = dict(self._bucket_counts)
            if not buckets:
                buckets = {f"<{b}": 0 for b in LATENCY_BUCKETS}
                buckets[">=1000"] = 0

            errors_in_last_n = sum(1 for x in self._recent_errors if x)
            return {
                "total_requests": self.total_requests,
                "errors_in_last_50": errors_in_last_n,
                "provider_usage": {
                    "keyword": self.provider_keyword_used,
                    "vector": self.provider_vector_used,
                },
                "vector_fallbacks": self.vector_fallbacks,
                "errors": self.errors,
                "latency": {
                    "avg_ms": round(avg_ms, 2),
                    "p50_ms": round(p50, 2),
                    "p95_ms": round(p95, 2),
                    "buckets": buckets,
                },
                "last_updated_at": self._last_updated_at.isoformat() if self._last_updated_at else None,
            }


# Singleton instance
_metrics: RAGMetricsCollector | None = None


def get_metrics() -> RAGMetricsCollector:
    """Return the singleton metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = RAGMetricsCollector()
    return _metrics
