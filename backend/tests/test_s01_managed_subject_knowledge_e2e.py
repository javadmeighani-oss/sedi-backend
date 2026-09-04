"""GATE=SEDI-V1-BE-S01 — Track A managed/accountless I8 knowledge + Track B I4 audit.

Track A: Son Account → Mother MANAGED HS (linked_user_id=NULL) → ALS condition →
         subject-aware I8 knowledge → governed SCIS ALS evidence.

Track B: documents HARD_STOP — no governed non-chat I4 device input authority.
"""

from __future__ import annotations

import hashlib
import inspect
import os
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.health_subject_condition_service import report_subject_condition
from backend.app.services.i5.runtime_knowledge_retrieval import STATUS_OK
from backend.app.services.i8.knowledge_bridge import retrieve_governed_knowledge_for_subject
from backend.app.services.i8.subject_context import load_subject_trusted_context
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    ensure_self_subject_for_account,
)
from backend.app.services.managed_person_service import create_managed_person
from backend.app.services.scis.embedding.providers import FakeScisEmbeddingProvider
from backend.app.services.scis.indexing import index_knowledge_unit


ALS_QUERY = "What should be monitored in the daily care of a person with ALS?"


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
        if not conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'")).scalar():
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


def _user(db, name: str) -> models.User:
    row = models.User(name=name, secret_key=f"sk-{name}-{uuid4().hex[:6]}", preferred_language="en")
    db.add(row)
    db.flush()
    return row


def _als_catalog(db) -> models.MedicalCondition:
    row = db.query(models.MedicalCondition).filter(models.MedicalCondition.code == "ALS").first()
    if row:
        return row
    row = models.MedicalCondition(
        code="ALS",
        name="Amyotrophic Lateral Sclerosis",
        description="catalog",
        category="neurological",
    )
    db.add(row)
    db.flush()
    return row


def _index_als_ku(db):
    ts = datetime.utcnow().timestamp()
    digest = hashlib.sha256(f"s01-als-{ts}".encode()).hexdigest()
    ku = models.KnowledgeUnit(
        canonical_unit_id=f"s01-als-{ts}",
        immutable_version_id="v1",
        domain="neurology",
        language="en",
        knowledge_type="GUIDELINE",
        normalized_statement=(
            "Amyotrophic lateral sclerosis ALS also called Lou Gehrig's disease. "
            "ALS care education covers breathing, nutrition, and daily monitoring."
        ),
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
    index_knowledge_unit(db, ku, provider=FakeScisEmbeddingProvider())
    return ku


# ---------------------------------------------------------------------------
# Track B — authority audit (must remain HARD_STOP without inventing thresholds)
# ---------------------------------------------------------------------------


def test_s01_track_b_governed_nonchat_i4_input_missing():
    """No governed deterministic I4 device/non-chat input exists — do not invent thresholds."""
    from backend.app.services.intelligence.safety_risk import assess_safety_risk

    params = set(inspect.signature(assess_safety_risk).parameters)
    assert "message" in params
    forbidden = {"device_id", "packet", "vital", "heart_rate", "spo2", "ecg", "i9_observation"}
    assert params.isdisjoint(forbidden)

    # I9 package must not call assess_safety_risk (raw I9 ↛ I4).
    from pathlib import Path

    i9_root = Path(__file__).resolve().parents[1] / "app" / "services" / "i9"
    callers = []
    for path in i9_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "assess_safety_risk(" in text:
            callers.append(str(path))
    assert callers == []


# ---------------------------------------------------------------------------
# Track A — managed/accountless subject knowledge E2E
# ---------------------------------------------------------------------------


@pytestmark_db
def test_s01_managed_mother_i8_knowledge_e2e(db):
    als_cond = _als_catalog(db)
    ku = _index_als_ku(db)

    son = _user(db, "S01_SON")
    stranger = _user(db, "S01_STRANGER")
    son_self = ensure_self_subject_for_account(db, son.id, display_name="SON_SELF")
    mother, created = create_managed_person(
        db,
        account_user_id=son.id,
        display_name="MOTHER",
        access_role="MANAGER",
        idempotency_key=f"s01-mother-{uuid4().hex[:8]}",
    )
    assert created is True
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"

    hsc = report_subject_condition(
        db,
        actor_account_user_id=son.id,
        health_subject_id=mother.id,
        condition_id=als_cond.id,
        notes="caregiver-reported ALS for mother",
    )
    assert hsc.health_subject_id == mother.id
    db.commit()

    # Mother subject context carries ALS; actor ≠ patient
    mother_ctx = load_subject_trusted_context(
        db, actor_account_user_id=son.id, health_subject_id=mother.id
    )
    assert mother_ctx.actor_account_user_id == son.id
    assert mother_ctx.health_subject_id == mother.id
    assert mother_ctx.linked_user_id is None
    assert any("Amyotrophic" in c or "ALS" in c.upper() or "als" in c.lower() for c in mother_ctx.conditions) or any(
        "Lateral" in c for c in mother_ctx.conditions
    )

    # Subject-aware knowledge retrieval
    result = retrieve_governed_knowledge_for_subject(
        db,
        actor_account_user_id=son.id,
        health_subject_id=mother.id,
        query=ALS_QUERY,
        domain="lifestyle",
    )
    assert result.status == STATUS_OK
    assert result.items
    assert any(i.knowledge_unit_id == ku.id for i in result.items)
    assert all(i.immutable_version_id for i in result.items)
    assert all(str(i.memory_item_id).startswith("SCIS_KCE:") for i in result.items)
    snip = result.items[0].as_care_snippet()
    assert snip["citation"]["label"]
    assert result.user_id_scope == son.id  # actor Account audit scope

    # Son SELF must not inherit Mother ALS as subject identity for knowledge personalization
    son_ctx = load_subject_trusted_context(
        db, actor_account_user_id=son.id, health_subject_id=son_self.id
    )
    assert son_ctx.health_subject_id == son_self.id
    assert mother.id != son_self.id
    assert not any(hsc.id == r.get("ref_id") for r in son_ctx.condition_refs)

    # Unauthorized stranger fail-closed
    with pytest.raises(HealthSubjectAccessDenied):
        retrieve_governed_knowledge_for_subject(
            db,
            actor_account_user_id=stranger.id,
            health_subject_id=mother.id,
            query=ALS_QUERY,
        )

    # Unrelated managed subject isolation
    other, _ = create_managed_person(
        db,
        account_user_id=son.id,
        display_name="OTHER_PERSON",
        access_role="MANAGER",
        idempotency_key=f"s01-other-{uuid4().hex[:8]}",
    )
    assert other.id != mother.id
    other_ctx = load_subject_trusted_context(
        db, actor_account_user_id=son.id, health_subject_id=other.id
    )
    assert not any(r.get("ref_id") == hsc.id for r in other_ctx.condition_refs)

    # No account substitution: Mother remains without linked User
    db.refresh(mother)
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"
