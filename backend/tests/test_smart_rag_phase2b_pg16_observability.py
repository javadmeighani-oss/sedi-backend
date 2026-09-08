"""Phase2-B CASE28 — PG16 observability integration on canonical SCIS→I5 path.

Exercises real retrieve_knowledge_context + SCIS lexical indexing (Fake embed DI).
Skips when TEST_DATABASE_URL / pgvector unavailable (local). CI must execute.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.scis.embedding.providers import FakeScisEmbeddingProvider


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


def test_phase2b_pg16_observability_propagates_on_canonical_path(db):
    """Real SCIS→adapter→retrieve_knowledge_context observability (no full-path mock)."""
    from backend.app.services.i5.runtime_knowledge_retrieval import (
        STATUS_OK,
        retrieve_knowledge_context,
    )
    from backend.app.services.scis.indexing import index_knowledge_unit

    ts = datetime.utcnow().timestamp()
    ku = _make_ku(
        db,
        canonical=f"p2b-obs-sleep-{ts}",
        statement="Healthy sleep habits for adults include a regular bedtime routine.",
        domain="lifestyle",
    )
    index_knowledge_unit(db, ku, provider=FakeScisEmbeddingProvider())
    db.commit()

    # Force lexical via missing OpenAI network path is fine; Fake provider via resolve
    # may still hybrid when allow_network+key. Explicitly force lexical by env absence
    # and allow_network True still resolves lexical without key — product path.
    result = retrieve_knowledge_context(
        db,
        "healthy sleep habits for adults",
        language="en",
        limit=3,
        enqueue_gap_on_empty=False,
    )

    assert result.status == STATUS_OK
    assert result.items
    obs = result.observability
    assert obs.get("retrieval_mode") in {"lexical", "hybrid", "scis_lexical", "scis_hybrid"} or obs.get(
        "effective_mode"
    ) in {"lexical", "hybrid"}
    # Prefer canonical keys from CASE28 envelope.
    mode = obs.get("retrieval_mode") or obs.get("effective_mode")
    assert mode in {"lexical", "hybrid"}
    assert obs.get("language") == "en"
    assert isinstance(obs.get("lexical_count"), int)
    assert obs["lexical_count"] >= 1
    assert isinstance(obs.get("final_evidence_count"), int)
    assert obs["final_evidence_count"] == len(result.items)
    assert obs.get("fallback_state") is not None
    assert "provider" in obs
    # timings/latency when SCIS supplied them
    assert "latency_ms" in obs or "timings_ms" in obs
    if obs.get("timings_ms"):
        assert isinstance(obs["timings_ms"], dict)
    # governance drop counts present (may be empty dict)
    assert "governance_drop_counts" in obs
    assert isinstance(obs["governance_drop_counts"], dict)
    assert obs.get("coreference_state") == "NOT_APPLICABLE"
    assert "clarification_required" in obs

    # Privacy: no raw content / secrets in observability
    blob = str(obs).lower()
    assert "healthy sleep habits" not in blob
    assert "embedding" not in blob or "embedding" not in obs  # no vector payload key
    assert "api_key" not in blob
    assert "authorization" not in blob
    assert "chunk_content" not in obs
    assert "original_query" not in obs
    # Original query preserved separately; observability does not own it.
    assert result.original_query == "healthy sleep habits for adults"
    # Observability did not mutate authority of returned items.
    assert all(i.as_care_snippet()["authority_label"] == "GOVERNED" for i in result.items)
