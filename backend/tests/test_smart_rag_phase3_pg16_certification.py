"""Phase3 PG16 certification — canonical SCIS→I5 path for cross-case A/C locks."""

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
from backend.app.services.scis.contracts import FallbackState


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


def test_phase3_pg16_en_governed_retrieval_observability(db):
    from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK, retrieve_knowledge_context
    from backend.app.services.scis.indexing import index_knowledge_unit

    ts = datetime.utcnow().timestamp()
    ku = _make_ku(
        db,
        canonical=f"p3-en-{ts}",
        statement="Regular hydration supports general adult wellness routines.",
        language="en",
    )
    index_knowledge_unit(db, ku, provider=FakeScisEmbeddingProvider())
    db.commit()

    with patch(
        "backend.app.services.scis.governed_runtime_adapter.resolve_product_governed_embedding",
        return_value=(FakeScisEmbeddingProvider(), "hybrid"),
    ):
        result = retrieve_knowledge_context(
            db, "hydration wellness routines", language="en", limit=3, enqueue_gap_on_empty=False
        )
    assert result.status == STATUS_OK
    assert result.items
    obs = result.observability
    assert obs.get("language") == "en"
    assert obs.get("cohere_used") is False
    assert obs.get("stage17_rag_embeddings_used") is False
    assert result.items[0].as_care_snippet()["authority_label"] == "GOVERNED"


def test_phase3_pg16_timeout_fallback_lexical(db):
    from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context
    from backend.app.services.scis.indexing import index_knowledge_unit

    ts = datetime.utcnow().timestamp()
    ku = _make_ku(
        db,
        canonical=f"p3-fb-{ts}",
        statement="Evening stretching may support general adult mobility habits.",
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
            db, "evening stretching mobility", language="en", limit=3, enqueue_gap_on_empty=False
        )
    obs = result.observability
    assert obs.get("cohere_used") is False
    assert obs.get("stage17_rag_embeddings_used") is False
    assert obs.get("openai_failure_lexical_fallback") is True or obs.get("retrieval_mode") in {
        "lexical",
        "hybrid",
        "scis_lexical",
        "scis_hybrid",
    }


def test_phase3_pg16_case04_negation_polarity_fail_closed(db):
    """Opposite-polarity fixtures: negated query must not equal affirmative FTS path."""
    from backend.app.services.scis.contracts import RetrievalMode, ScisRetrievalRequest
    from backend.app.services.scis.embedding.providers import FakeScisEmbeddingProvider
    from backend.app.services.scis.indexing import index_knowledge_unit
    from backend.app.services.scis.lexical import lexical_search
    from backend.app.services.scis.lexical_query import formulate_lexical_query_plan
    from backend.app.services.scis.retrieval import retrieve

    ts = datetime.utcnow().timestamp()
    ku_a = _make_ku(
        db,
        canonical=f"p3-neg-a-{ts}",
        statement="Emergency warning signs require urgent evaluation.",
    )
    ku_b = _make_ku(
        db,
        canonical=f"p3-neg-b-{ts}",
        statement="Non-emergency routine monitoring guidance for wellness adults.",
    )
    index_knowledge_unit(db, ku_a, provider=FakeScisEmbeddingProvider())
    index_knowledge_unit(db, ku_b, provider=FakeScisEmbeddingProvider())
    db.commit()

    aff_plan = formulate_lexical_query_plan("emergency", language="en")
    neg_plan = formulate_lexical_query_plan("not emergency", language="en")
    assert aff_plan.primary_query != neg_plan.primary_query
    assert neg_plan.negation_present is True
    assert neg_plan.primary_query == ""

    aff_rows, aff_meta = lexical_search(db, "emergency", language="en", top_k=10)
    neg_rows, neg_meta = lexical_search(db, "not emergency", language="en", top_k=10)
    assert aff_meta.get("negation_lexical_blocked") is not True
    assert neg_meta.get("negation_lexical_blocked") is True
    assert neg_rows == []
    # Affirmative FTS may hit emergency fixture; negated must not silently reuse that path.
    assert not (neg_rows and aff_rows and {c.chunk_id for c in neg_rows} == {c.chunk_id for c in aff_rows})

    failing = FakeScisEmbeddingProvider()
    failing.provider_name = "openai"  # type: ignore[misc]
    failing.model_identifier = "text-embedding-3-large"  # type: ignore[misc]

    def boom(*_a, **_k):
        raise OpenAIEmbeddingFailure(ERROR_OPENAI_TIMEOUT)

    failing.embed_texts = boom  # type: ignore[method-assign]

    resp = retrieve(
        db,
        ScisRetrievalRequest(
            query_text="not emergency",
            query_language="en",
            top_k=5,
            retrieval_mode=RetrievalMode.HYBRID,
        ),
        provider=failing,
    )
    assert resp.evidence == []
    assert int((resp.filtered_counts or {}).get("negation_lexical_fail_closed") or 0) == 1
    assert resp.fallback_state == FallbackState.EMBEDDING_FAILURE
