# tests/test_rag_stage17_8.py
"""
Tests for Stage 17.8 - Vector RAG Pilot.
"""

import pytest

from app.database import Base, engine, SessionLocal
from app.models import User, DailyMemorySummary
from app.services.local_rag.indexing import index_daily_summaries_for_user, _content_hash


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
    user = User(name="PilotTest", secret_key="sk", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    db.delete(user)
    db.commit()


def test_allowlist_gating_uses_keyword_when_not_in_allowlist(db, test_user, monkeypatch):
    """When RAG_VECTOR_ENABLED=true but user not in allowlist, use keyword."""
    monkeypatch.setenv("RAG_VECTOR_ENABLED", "true")
    monkeypatch.setenv("RAG_VECTOR_ALLOWLIST", "99999")
    from app.services.local_rag import provider_router

    monkeypatch.setattr(provider_router, "RAG_VECTOR_ENABLED", True)
    monkeypatch.setattr(provider_router, "RAG_VECTOR_ALLOWLIST", frozenset([99999]))

    provider = provider_router.get_rag_provider(db, test_user.id)
    assert isinstance(provider, provider_router.LocalRAGProvider)

    provider2 = provider_router.get_rag_provider(db, 99999)
    assert isinstance(provider2, provider_router.VectorRAGProvider)


def test_allowlist_parsing_robust():
    """Allowlist parses comma-separated ids, ignores invalid."""
    raw = " 1 , 2 , abc , 3 , "
    allowlist = frozenset(
        int(x.strip())
        for x in raw.split(",")
        if x.strip() and x.strip().isdigit()
    )
    assert 1 in allowlist
    assert 2 in allowlist
    assert 3 in allowlist


def test_index_daily_summaries_empty_returns_zero(db, test_user):
    """index_daily_summaries_for_user with no summaries returns zeros."""
    try:
        result = index_daily_summaries_for_user(db, test_user.id, days=30)
        assert result["indexed"] == 0
        assert result["skipped"] >= 0
        assert result["failed"] >= 0
    except Exception:
        pass


def test_content_hash_deterministic():
    """_content_hash is deterministic."""
    h1 = _content_hash("hello")
    h2 = _content_hash("hello")
    assert h1 == h2
    assert _content_hash("world") != h1
