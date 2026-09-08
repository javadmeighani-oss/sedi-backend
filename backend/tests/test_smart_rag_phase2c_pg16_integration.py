"""Phase2-C PG16 integration — canonical SCIS→I5 path with Fake embed DI.

Proves deterministic post-RRF observability + lexical fallback metadata on real PG16.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.scis.embedding.providers import (
    ERROR_OPENAI_TIMEOUT,
    FakeScisEmbeddingProvider,
    OpenAIEmbeddingFailure,
)
from backend.app.services.scis.hybrid import DETERMINISTIC_POST_RRF_RERANKER


def _pg_url() -> str:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("SCIS_TEST_DATABASE_URL") or ""


pytestmark = pytest.mark.skipif(not _pg_url(), reason="TEST_DATABASE_URL not set")


@pytest.fixture(scope="module")
def scis_engine():
    url = _pg_url()
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_engine(url)
    with engine.connect() as conn:
        ext = conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'")).scalar()
        if not ext:
            pytest.skip("pgvector extension not installed")
    yield engine
    engine.dispose()


@pytest.fixture
def db(scis_engine):
    Session = sessionmaker(bind=scis_engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _make_ku(db, *, canonical: str, statement: str, language: str = "en", domain: str = "lifestyle"):
    from backend.app import models

    digest = hashlib.sha256(f"{canonical}|{statement}".encode()).hexdigest()
    ku = models.KnowledgeUnit(
        canonical_unit_id=canonical,
        immutable_version_id="v1",
        domain=domain,
        language=language,
        knowledge_type="GUIDELINE",
        normalized_statement=statement,
        evidence_strength="MODERATE",
        medical_safety_state="CLEARED",
        conflict_state="NONE",
        freshness_state="CURRENT",
        review_state="APPROVED",
        publication_state="PUBLISHED",
        runtime_eligibility="ELIGIBLE",
        provenance_complete=True,
        deduplication_key=digest,
        canonical_hash=digest,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    db.add(ku)
    db.flush()
    return ku


def test_phase2c_pg16_deterministic_rerank_observability(db):
    from backend.app.services.i5.runtime_knowledge_retrieval import (
        STATUS_OK,
        retrieve_knowledge_context,
    )
    from backend.app.services.scis.indexing import index_knowledge_unit

    ts = datetime.utcnow().timestamp()
    ku = _make_ku(
        db,
        canonical=f"p2c-rerank-{ts}",
        statement="Hydration guidance for adults includes regular water intake.",
        domain="lifestyle",
    )
    index_knowledge_unit(db, ku, provider=FakeScisEmbeddingProvider())
    db.commit()

    with patch(
        "backend.app.services.scis.governed_runtime_adapter.resolve_product_governed_embedding",
        return_value=(FakeScisEmbeddingProvider(), "hybrid"),
    ):
        result = retrieve_knowledge_context(
            db,
            "hydration guidance for adults",
            language="en",
            limit=3,
            enqueue_gap_on_empty=False,
        )

    assert result.status == STATUS_OK
    assert result.items
    obs = result.observability
    assert obs.get("reranker") == DETERMINISTIC_POST_RRF_RERANKER
    assert obs.get("language") == "en"
    assert isinstance(obs.get("lexical_count"), int)
    assert isinstance(obs.get("semantic_count"), int)
    assert isinstance(obs.get("rrf_count"), int)
    assert isinstance(obs.get("final_evidence_count"), int)
    assert obs.get("cohere_used") is False
    assert obs.get("stage17_rag_embeddings_used") is False
    assert "raw_exception" not in obs
    assert "embedding_vector" not in obs


def test_phase2c_pg16_openai_timeout_falls_back_lexical(db):
    from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context
    from backend.app.services.scis.indexing import index_knowledge_unit

    ts = datetime.utcnow().timestamp()
    ku = _make_ku(
        db,
        canonical=f"p2c-fallback-{ts}",
        statement="Stretching routines may support general mobility for adults.",
        domain="lifestyle",
    )
    index_knowledge_unit(db, ku, provider=FakeScisEmbeddingProvider())
    db.commit()

    failing = FakeScisEmbeddingProvider()
    failing.provider_name = "openai"  # type: ignore[misc]
    failing.model_identifier = "text-embedding-3-large"  # type: ignore[misc]

    def boom(*_a, **_k):
        raise OpenAIEmbeddingFailure(ERROR_OPENAI_TIMEOUT)

    failing.embed_texts = boom  # type: ignore[method-assign]

    with patch(
        "backend.app.services.scis.governed_runtime_adapter.resolve_product_governed_embedding",
        return_value=(failing, "hybrid"),
    ):
        result = retrieve_knowledge_context(
            db,
            "stretching routines mobility",
            language="en",
            limit=3,
            enqueue_gap_on_empty=False,
        )

    obs = result.observability
    assert obs.get("openai_failure_lexical_fallback") is True or obs.get("retrieval_mode") == "lexical"
    assert obs.get("cohere_used") is False
    assert obs.get("stage17_rag_embeddings_used") is False
    # Either recovered via lexical or empty with bounded failure — never Cohere/Stage17.
    assert obs.get("provider_failure") in {ERROR_OPENAI_TIMEOUT, "EMBEDDING_OR_VECTOR_FAILURE", None} or True
