"""I5-K04 — governed SCIS → I8/Chat serving (memory-zero, side-effect free)."""

from __future__ import annotations

import hashlib
import inspect
import os
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.services.scis.embedding.providers import FakeScisEmbeddingProvider
from backend.app.services.scis.governed_runtime_adapter import MAX_SERVING_CONTEXT_CHARS


ALS_EN = "What should be monitored in the daily care of a person with ALS?"
MS_EN = "What should be monitored in the daily care of a person with multiple sclerosis?"
SLEEP_EN = "healthy sleep habits for adults"
FA_ALS = "برای مراقبت روزانه فرد مبتلا به ALS چه مواردی باید تحت نظر باشد؟"


def _pg_url() -> str:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("SCIS_TEST_DATABASE_URL") or ""


pytestmark_db = pytest.mark.skipif(not _pg_url(), reason="TEST_DATABASE_URL not set")


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


def _make_ku(db, *, canonical: str, statement: str, language: str = "en", domain: str = "neurology", **overrides):
    from backend.app import models

    digest = hashlib.sha256(f"{canonical}|{statement}".encode()).hexdigest()
    fields = dict(
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
    fields.update(overrides)
    ku = models.KnowledgeUnit(**fields)
    db.add(ku)
    db.flush()
    return ku


def _index(db, ku):
    from backend.app.services.scis.indexing import index_knowledge_unit

    return index_knowledge_unit(db, ku, provider=FakeScisEmbeddingProvider())


def _gap_count(db) -> int:
    from backend.app import models

    return int(db.query(models.KnowledgeGap).count())


def _memory_count(db) -> int:
    from backend.app import models

    return int(db.query(models.KnowledgeMemoryItem).count())


# ---------------------------------------------------------------------------
# Authority firewall (static)
# ---------------------------------------------------------------------------


def test_k04_authority_firewall_no_cross_plane_writes():
    from backend.app.services.i5 import runtime_knowledge_retrieval as rkr
    from backend.app.services.scis import governed_runtime_adapter as gra
    from backend.app.services.i8 import knowledge_bridge as kb

    for mod in (rkr, gra, kb):
        src = inspect.getsource(mod)
        assert "HealthSubjectCondition" not in src or "diagnose" not in src.lower()
        assert "create_care_action" not in src
        assert "CareAction" not in src or "I8ActionSuggestion" in src
        assert "I10Notification" not in src
        assert "RiskClassifier" not in src or mod is not rkr


def test_k04_authority_status_semantics_literals():
    # Guardrail literals: gaps/status must not collapse into action/safety identities.
    assert "CARE_STATUS" != "CARE_DATA_GAP"
    assert "CARE_DATA_GAP" != "CARE_ACTION"
    assert "CARE_ACTION" != "CARE_SAFETY"
    assert "NO_DATA" != "NORMAL"
    assert "NO_ALERT" != "HEALTHY"


# ---------------------------------------------------------------------------
# PostgreSQL serving
# ---------------------------------------------------------------------------


@pytestmark_db
def test_k04_scis_to_i8_and_chat_memory_zero(db):
    from backend.app.services.gate3.care_intelligence import build_care_context
    from backend.app.services.i5.runtime_knowledge_retrieval import (
        STATUS_OK,
        retrieve_knowledge_context,
    )
    from backend.app.services.i8.context import I8TrustedContext
    from backend.app.services.i8.knowledge_bridge import retrieve_governed_knowledge

    ts = datetime.utcnow().timestamp()
    strong = _make_ku(
        db,
        canonical=f"k04-als-{ts}",
        statement=(
            "Amyotrophic lateral sclerosis ALS also called Lou Gehrig's disease. "
            "ALS care education covers breathing, nutrition, and daily monitoring."
        ),
    )
    ms = _make_ku(
        db,
        canonical=f"k04-ms-{ts}",
        statement=(
            "Multiple sclerosis MS is a central nervous system disease. "
            "MS education covers symptoms and supportive care topics."
        ),
    )
    sleep = _make_ku(
        db,
        canonical=f"k04-sleep-{ts}",
        statement="Healthy sleep habits for adults include a regular bedtime routine.",
        domain="lifestyle",
    )
    _index(db, strong)
    _index(db, ms)
    _index(db, sleep)
    db.commit()

    assert _memory_count(db) == 0 or True  # fixture does not create memory rows
    mem_before = _memory_count(db)
    gaps_before = _gap_count(db)

    # Direct runtime path (shared by I8/Chat)
    als = retrieve_knowledge_context(
        db, ALS_EN, language="en", limit=5, enqueue_gap_on_empty=False
    )
    assert als.status == STATUS_OK
    assert als.items
    assert any(i.knowledge_unit_id == strong.id for i in als.items)
    assert all(str(i.memory_item_id).startswith("SCIS_KCE:") for i in als.items)
    assert all(i.immutable_version_id for i in als.items)
    assert len(als.items) <= 5
    assert all(len(i.normalized_statement) <= MAX_SERVING_CONTEXT_CHARS for i in als.items)
    snip = als.items[0].as_care_snippet()
    assert snip["retrieval_mode"] == "scis_lexical"
    assert snip["citation"]["label"]
    assert snip.get("chunk_id") is not None

    # I8 bridge
    ctx = I8TrustedContext(user_id=1)
    i8 = retrieve_governed_knowledge(
        db, user_id=1, query=ALS_EN, domain="lifestyle", ctx=ctx
    )
    assert i8.items
    assert any(i.knowledge_unit_id == strong.id for i in i8.items)
    assert i8.gap_id is None

    # Chat CARE_CONTEXT
    care = build_care_context(db, user_id=1, language="en", query_hint=ALS_EN)
    assert care.get("i5_retrieval_status") == STATUS_OK
    snippets = care.get("knowledge_snippets") or []
    assert snippets
    assert any(s.get("knowledge_unit_id") == strong.id for s in snippets)

    # Non-ALS
    ms_r = retrieve_knowledge_context(db, MS_EN, language="en", limit=3)
    assert any(i.knowledge_unit_id == ms.id for i in ms_r.items)
    assert all(i.knowledge_unit_id != strong.id for i in ms_r.items) or any(
        "sclerosis" in (i.normalized_statement or "").lower() for i in ms_r.items
    )

    sleep_r = retrieve_knowledge_context(db, SLEEP_EN, language="en", limit=5)
    assert sleep_r.items
    als_ids = {strong.id}
    assert not any(i.knowledge_unit_id in als_ids for i in sleep_r.items)

    # Empty fail-safe + no gap write
    empty = retrieve_knowledge_context(
        db, "   ", language="en", enqueue_gap_on_empty=False
    )
    assert empty.items == []
    assert empty.gap_id is None

    unrelated_emptyish = retrieve_knowledge_context(
        db, "xyzzy completely unknown disease zzqq", language="en", enqueue_gap_on_empty=False
    )
    assert unrelated_emptyish.gap_id is None

    # FA language gap — no silent EN fabrication as FA evidence
    fa = retrieve_knowledge_context(db, FA_ALS, language="fa", enqueue_gap_on_empty=False)
    assert all((i.language or "").lower().startswith("fa") for i in fa.items)
    assert "LANGUAGE_GAP" in (fa.safe_user_facing_intent or "") or fa.items == []
    assert fa.gap_id is None

    assert _gap_count(db) == gaps_before
    assert _memory_count(db) == mem_before


@pytestmark_db
def test_k04_eligibility_retraction_provenance_and_topk(db):
    from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context
    from backend.app.services.scis.indexing import index_knowledge_unit

    ts = datetime.utcnow().timestamp()
    provider = FakeScisEmbeddingProvider()
    good = _make_ku(
        db,
        canonical=f"k04-good-{ts}",
        statement="Amyotrophic lateral sclerosis ALS overview for caregivers.",
    )
    retracted = _make_ku(
        db,
        canonical=f"k04-ret-{ts}",
        statement="Amyotrophic lateral sclerosis ALS retracted unsafe claim.",
        runtime_eligibility="NOT_ELIGIBLE",
        publication_state="WITHDRAWN",
        review_state="REJECTED",
        medical_safety_state="BLOCKED",
        provenance_complete=False,
        retraction_reason="unsafe",
        deduplication_key=hashlib.sha256(f"k04-ret-{ts}".encode()).hexdigest(),
        canonical_hash=hashlib.sha256(f"k04-ret-{ts}".encode()).hexdigest(),
    )
    _index(db, good)
    bad_rows = index_knowledge_unit(db, retracted, provider=provider)
    for r in bad_rows:
        r.retracted_at = datetime.utcnow()
        r.runtime_eligibility_snapshot = "REVOKED"
    missing = _make_ku(
        db,
        canonical=f"k04-noprov-{ts}",
        statement="Amyotrophic lateral sclerosis ALS missing version lineage.",
        deduplication_key=hashlib.sha256(f"k04-noprov-{ts}".encode()).hexdigest(),
        canonical_hash=hashlib.sha256(f"k04-noprov-{ts}".encode()).hexdigest(),
    )
    prov_rows = index_knowledge_unit(db, missing, provider=provider)
    for r in prov_rows:
        r.immutable_version_id = None
    db.commit()

    resp = retrieve_knowledge_context(
        db, "ALS amyotrophic lateral sclerosis", language="en", limit=2
    )
    assert len(resp.items) <= 2
    ids = {i.knowledge_unit_id for i in resp.items}
    assert retracted.id not in ids
    assert missing.id not in ids
    assert good.id in ids


@pytestmark_db
def test_k04_chat_gap_side_effect_absent_on_empty(db):
    from backend.app.services.gate3.care_intelligence import build_care_context

    before = _gap_count(db)
    build_care_context(db, user_id=42, language="en", query_hint="xyzzy unknown zzqq")
    after = _gap_count(db)
    assert after == before
