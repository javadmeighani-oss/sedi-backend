# tests/test_rag_breaker.py
"""
Tests for Stage 17.9 - RAG circuit breaker guardrails.
"""

import pytest

from app.database import Base, engine, SessionLocal
from app.models import User


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_user(db):
    user = User(name="BreakerTest", secret_key="sk", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


def test_breaker_trips_when_p95_exceeded(monkeypatch):
    """Circuit breaker trips when p95 latency exceeds threshold."""
    monkeypatch.setenv("RAG_VECTOR_P95_MAX_MS", "100")
    monkeypatch.setenv("RAG_VECTOR_ERROR_MAX", "10")
    monkeypatch.setenv("RAG_VECTOR_FALLBACK_TTL_SECONDS", "60")
    import importlib
    import app.services.local_rag.circuit_breaker as cb
    importlib.reload(cb)

    snapshot = {"latency": {"p95_ms": 150}, "errors_in_last_50": 0}
    cb.check_after_request(snapshot)
    assert cb.is_tripped() is True
    state = cb.get_state()
    assert state["is_tripped"] is True
    assert "p95" in (state.get("last_reason") or "")


def test_breaker_trips_when_errors_exceeded(monkeypatch):
    """Circuit breaker trips when errors in last 50 exceed threshold."""
    monkeypatch.setenv("RAG_VECTOR_P95_MAX_MS", "1000")
    monkeypatch.setenv("RAG_VECTOR_ERROR_MAX", "3")
    monkeypatch.setenv("RAG_VECTOR_FALLBACK_TTL_SECONDS", "60")
    import importlib
    import app.services.local_rag.circuit_breaker as cb
    importlib.reload(cb)

    snapshot = {"latency": {"p95_ms": 50}, "errors_in_last_50": 5}
    cb.check_after_request(snapshot)
    assert cb.is_tripped() is True
    state = cb.get_state()
    assert "errors" in (state.get("last_reason") or "")


def test_breaker_prevents_vector_usage_when_tripped(db, test_user, monkeypatch):
    """When breaker is tripped, get_rag_provider returns keyword provider."""
    monkeypatch.setenv("RAG_VECTOR_ENABLED", "true")
    monkeypatch.setenv("RAG_VECTOR_P95_MAX_MS", "1")
    monkeypatch.setenv("RAG_VECTOR_FALLBACK_TTL_SECONDS", "3600")
    import importlib
    import app.services.local_rag.circuit_breaker as cb
    importlib.reload(cb)
    import app.services.local_rag.provider_router as pr

    monkeypatch.setattr(pr, "RAG_VECTOR_ENABLED", True)
    monkeypatch.setattr(pr, "RAG_VECTOR_ALLOWLIST", frozenset([test_user.id]))

    cb.check_after_request({"latency": {"p95_ms": 999}, "errors_in_last_50": 0})
    assert cb.is_tripped() is True

    provider = pr.get_rag_provider(db, test_user.id)
    assert isinstance(provider, pr.LocalRAGProvider)
