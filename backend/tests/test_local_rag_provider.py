# tests/test_local_rag_provider.py
"""
Tests for Stage 17.5 - Local RAG provider.
"""

import pytest
from datetime import datetime, timedelta

from app.database import Base, engine, SessionLocal
from app.models import User, UserFact, UserMemoryFact, DailyMemorySummary, Memory, UserProfileKnowledge
from app.services.local_rag.local_provider import LocalRAGProvider, RAG_LOCAL_TOP_K, RAG_LOCAL_MAX_CHARS


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
    user = User(name="RagTest", secret_key="sk", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


def test_retrieval_returns_sources(db, test_user):
    """Retrieval returns sources when data exists."""
    uf = UserFact(
        user_id=test_user.id,
        key="sleep_key",
        value_json='7.5',
        source="manual",
    )
    db.add(uf)
    db.commit()

    provider = LocalRAGProvider(db)
    result = provider.retrieve(test_user.id, "sleep lifestyle", "en")

    assert result is not None
    assert result.sources is not None
    assert len(result.sources) >= 1
    assert any(s.get("type") == "user_fact" for s in result.sources)


def test_retrieval_respects_top_k(db, test_user, monkeypatch):
    """Retrieval respects RAG_LOCAL_TOP_K."""
    monkeypatch.setenv("RAG_LOCAL_TOP_K", "3")

    for i in range(8):
        uf = UserFact(
            user_id=test_user.id,
            key=f"key_{i}",
            value_json=f'"{i}"',
            source="manual",
        )
        db.add(uf)
    db.commit()

    from app.services.local_rag import local_provider
    monkeypatch.setattr(local_provider, "RAG_LOCAL_TOP_K", 3)

    provider = LocalRAGProvider(db)
    result = provider.retrieve(test_user.id, "lifestyle", "en")

    assert len(result.chunks) <= 3


def test_retrieval_respects_max_chars(db, test_user, monkeypatch):
    """Retrieval combined_text is bounded by RAG_LOCAL_MAX_CHARS."""
    monkeypatch.setenv("RAG_LOCAL_MAX_CHARS", "500")

    long_text = "x " * 500
    uf = UserFact(
        user_id=test_user.id,
        key="big",
        value_json=repr(long_text),
        source="manual",
    )
    db.add(uf)
    db.commit()

    from app.services.local_rag import local_provider
    monkeypatch.setattr(local_provider, "RAG_LOCAL_MAX_CHARS", 500)

    provider = LocalRAGProvider(db)
    result = provider.retrieve(test_user.id, "big", "en")

    assert len(result.combined_text) <= 500


def test_no_error_when_no_data(db, test_user):
    """Does not error when user has no data."""
    provider = LocalRAGProvider(db)
    result = provider.retrieve(test_user.id, "lifestyle summary", "en")

    assert result is not None
    assert result.chunks is not None
    assert result.sources is not None
    assert result.combined_text == "" or isinstance(result.combined_text, str)


# -------------------- Stage 17.6 Provider Router --------------------
def test_provider_router_uses_keyword_when_vector_disabled(db, test_user, monkeypatch):
    """Provider router returns keyword provider when RAG_VECTOR_ENABLED=false."""
    monkeypatch.setenv("RAG_VECTOR_ENABLED", "false")
    from app.services.local_rag import provider_router
    monkeypatch.setattr(provider_router, "RAG_VECTOR_ENABLED", False)

    provider = provider_router.get_rag_provider(db, test_user.id)
    assert isinstance(provider, LocalRAGProvider)

    result = provider_router.retrieve(db, test_user.id, "lifestyle", "en")
    assert result is not None
    assert hasattr(result, "combined_text")
    assert hasattr(result, "sources")


def test_provider_router_falls_back_to_keyword_when_vector_unavailable(db, test_user, monkeypatch):
    """When RAG_VECTOR_ENABLED=true but vector fails, retrieve falls back to keyword."""
    monkeypatch.setenv("RAG_VECTOR_ENABLED", "true")
    from app.services.local_rag import provider_router
    monkeypatch.setattr(provider_router, "RAG_VECTOR_ENABLED", True)

    result = provider_router.retrieve(db, test_user.id, "lifestyle", "en")
    assert result is not None
    assert hasattr(result, "combined_text")
    assert hasattr(result, "sources")


@pytest.mark.skipif(
    True,  # Vector provider raises; skip vector-specific test when pgvector not in test env
    reason="Vector provider requires pgvector; run with pgvector available to test",
)
def test_vector_provider_when_pgvector_available(db, test_user):
    """Vector provider retrieve works when pgvector is available. Skipped by default."""
    from app.services.local_rag.vector_provider import VectorRAGProvider

    provider = VectorRAGProvider(db)
    result = provider.retrieve(test_user.id, "test", "en")
    assert result is not None
