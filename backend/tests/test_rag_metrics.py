# tests/test_rag_metrics.py
"""
Tests for Stage 17.7 - RAG metrics.
"""

import pytest

from app.database import Base, engine, SessionLocal
from app.models import User
from app.services.local_rag.metrics import RAGMetricsCollector, get_metrics


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = next(SessionLocal())
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db):
    user = User(name="MetricsTest", secret_key="sk", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


def test_record_increments_counters():
    """record() increments total_requests and provider counters."""
    m = RAGMetricsCollector()
    m.record(success=True, provider_used="keyword", latency_ms=25, top_k=5, sources_count=4, fallback_used=False)
    m.record(success=True, provider_used="keyword", latency_ms=30, top_k=3, sources_count=3, fallback_used=False)
    m.record(success=True, provider_used="vector", latency_ms=80, top_k=6, sources_count=6, fallback_used=False)

    s = m.snapshot()
    assert s["total_requests"] == 3
    assert s["provider_usage"]["keyword"] == 2
    assert s["provider_usage"]["vector"] == 1
    assert s["vector_fallbacks"] == 0
    assert s["errors"] == 0


def test_record_fallback_increments():
    """record() with fallback_used=True increments vector_fallbacks."""
    m = RAGMetricsCollector()
    m.record(success=True, provider_used="keyword", latency_ms=20, top_k=4, sources_count=4, fallback_used=True)

    s = m.snapshot()
    assert s["vector_fallbacks"] == 1


def test_record_error_increments():
    """record() with success=False increments errors."""
    m = RAGMetricsCollector()
    m.record(success=False, provider_used="keyword", latency_ms=10, top_k=0, sources_count=0, fallback_used=False)

    s = m.snapshot()
    assert s["errors"] == 1


def test_latency_buckets():
    """record() populates latency buckets."""
    m = RAGMetricsCollector()
    m.record(success=True, provider_used="keyword", latency_ms=25, top_k=1, sources_count=1, fallback_used=False)
    m.record(success=True, provider_used="keyword", latency_ms=150, top_k=1, sources_count=1, fallback_used=False)
    m.record(success=True, provider_used="keyword", latency_ms=1200, top_k=1, sources_count=1, fallback_used=False)

    s = m.snapshot()
    assert "latency" in s
    assert "buckets" in s["latency"]
    assert s["latency"]["avg_ms"] > 0
    assert s["latency"]["p50_ms"] >= 0
    assert s["latency"]["p95_ms"] >= 0


def test_provider_router_records_fallback(db, test_user, monkeypatch):
    """provider_router records fallback when vector unavailable (user in allowlist)."""
    from app.services.local_rag.metrics import get_metrics
    from app.services.local_rag import provider_router

    monkeypatch.setenv("RAG_VECTOR_ENABLED", "true")
    monkeypatch.setattr(provider_router, "RAG_VECTOR_ENABLED", True)
    monkeypatch.setattr(provider_router, "RAG_VECTOR_ALLOWLIST", frozenset([test_user.id]))

    metrics = get_metrics()
    before_fallbacks = metrics.vector_fallbacks
    before_total = metrics.total_requests

    result = provider_router.retrieve(db, test_user.id, "lifestyle", "en")

    assert result is not None
    assert metrics.total_requests > before_total
    # Vector will fail (pgvector not in test env), so fallback should have been used
    assert metrics.vector_fallbacks > before_fallbacks
