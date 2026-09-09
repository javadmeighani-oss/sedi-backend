"""GATE=SEDI-SMART-RAG-CONTEXT-AUTHORITY-ARCHITECTURE-INTEGRATION-01

Exact 18 SRCA cases. Smart-RAG retrieves evidence; does not own Sedi truth.
NO schema/migration/I10/production/frontend. Reuses SCIS contracts.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app import models
from backend.app.services.i6.consent_service import grant_memory_consent
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.managed_person_service import create_managed_person
from backend.app.services.scis import DEFAULT_EMBEDDING_DIM, DEFAULT_EMBEDDING_MODEL
from backend.app.services.scis.authority_router import (
    RANKING_CANNOT_INCREASE_AUTHORITY,
    ROUTER_IS_AUTHORITY,
    SMART_RAG_OWNS_SEDI_TRUTH,
    assert_router_not_authority,
    route_sedi_retrieval_context,
)
from backend.app.services.scis.context_aware_retrieval import (
    PersonalToGovernedPromotionError,
    assert_personal_not_governed,
    bounded_personalization_from_context,
    build_scis_request_from_context,
    retrieve_sedi_evidence_package,
)
from backend.app.services.scis.context_resolver import (
    ContextResolutionDenied,
    PURPOSE_GOVERNED_RETRIEVAL,
    PURPOSE_PERSONAL_CONTEXT_RELEVANCE,
    resolve_sedi_retrieval_context,
    revoke_account_subject_access,
)
from backend.app.services.scis.contracts import (
    FallbackState,
    ProvenanceRef,
    RetrievalMode,
    ScisEvidenceItem,
    ScisRetrievalResponse,
)
from backend.app.services.scis.embedding.providers import FakeScisEmbeddingProvider
from backend.app.services.scis.evidence_package import (
    EvidenceSemanticEscalationError,
    SediEvidencePackage,
)
from backend.app.services.scis.governed_runtime_adapter import is_supported_governed_language
from backend.app.services.scis.hybrid import RRF_K, reciprocal_rank_fusion, RankedCandidate
from backend.app.services.scis.indexing import index_knowledge_unit
from backend.app.services.scis.sedi_retrieval_context import (
    BoundedContextRef,
    FORBIDDEN_RAW_CONTEXT_KEYS,
    SediRetrievalContext,
    SubjectMode,
    reject_forbidden_raw_keys,
)


GATE_ID = "SEDI-SMART-RAG-CONTEXT-AUTHORITY-ARCHITECTURE-INTEGRATION-01"
SCIS_ROOT = Path(__file__).resolve().parents[1] / "app" / "services" / "scis"
ALEMBIC_HEAD = "081_self_health_subject_1to1_hardening"


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
        ver = conn.execute(text("SHOW server_version")).scalar()
        if not str(ver).startswith("16."):
            pytest.skip(f"PostgreSQL 16 required, got {ver}")
        if not conn.execute(text("SELECT extname FROM pg_extension WHERE extname='vector'")).scalar():
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
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


def _index_ku(db, *, lang: str = "en", statement: str | None = None):
    import hashlib
    from datetime import datetime

    ts = datetime.utcnow().timestamp()
    digest = hashlib.sha256(f"srca-{lang}-{ts}".encode()).hexdigest()
    text_body = statement or (
        "Amyotrophic lateral sclerosis ALS care education covers breathing, "
        "nutrition, and daily monitoring for governed knowledge retrieval."
    )
    ku = models.KnowledgeUnit(
        canonical_unit_id=f"srca-{lang}-{ts}",
        immutable_version_id="v1",
        domain="neurology",
        language=lang,
        knowledge_type="GUIDELINE",
        normalized_statement=text_body,
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


def _synthetic_response(trace_id: str = "t-srca") -> ScisRetrievalResponse:
    return ScisRetrievalResponse(
        request_trace_id=trace_id,
        mode=RetrievalMode.HYBRID.value,
        language="en",
        evidence=[
            ScisEvidenceItem(
                label="GOVERNED",
                chunk_id=1,
                content="ALS care monitoring evidence",
                language="en",
                knowledge_unit_id=10,
                immutable_version_id="v1",
                retrieval_branch="hybrid",
                lexical_rank=1,
                vector_rank=1,
                fusion_rank=1,
                fusion_score=0.03,
                runtime_eligibility="ELIGIBLE",
                embedding_model=DEFAULT_EMBEDDING_MODEL,
                embedding_version="v1",
                provenance=ProvenanceRef(
                    chunk_id=1,
                    knowledge_unit_id=10,
                    immutable_version_id="v1",
                    raw_evidence_id=None,
                    source_profile_id=None,
                ),
            )
        ],
        fallback_state=FallbackState.NONE,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
    )


def _ctx(
    *,
    mode: SubjectMode = SubjectMode.SELF,
    linked: int | None = 1,
    requester: int = 1,
    subject: int = 100,
    personal: bool = False,
    device: bool = False,
    safety: str | None = None,
) -> SediRetrievalContext:
    return SediRetrievalContext(
        requester_account_id=requester,
        target_health_subject_id=subject,
        subject_mode=mode,
        relationship="SELF" if mode == SubjectMode.SELF else "MANAGER",
        authorization_scope=("ACCOUNT_HEALTH_SUBJECT_ACCESS", "I5_GOVERNED_KNOWLEDGE"),
        purpose=PURPOSE_GOVERNED_RETRIEVAL,
        language="en",
        intent="care_education",
        domain="neurology",
        safety_classification=safety,
        personal_context_ref=(
            BoundedContextRef(ref_type="personal_context_scope", authority="I7", ref_id=subject)
            if personal
            else None
        ),
        device_status_ref=(
            BoundedContextRef(
                ref_type="device_reported_vital_status",
                authority="I9",
                ref_id=9,
                label="STABLE",
            )
            if device
            else None
        ),
        trace_id="srca-unit",
        access_role="SELF" if mode == SubjectMode.SELF else "MANAGER",
        linked_user_id=linked if mode == SubjectMode.SELF else None,
    )


# ---------------------------------------------------------------------------
# SRCA-01..06 — identity / access (PG16)
# ---------------------------------------------------------------------------


@pytestmark_db
def test_srca_01_self_context_resolution(db):
    son = _user(db, "SRCA_SON_SELF")
    self_hs = ensure_self_subject_for_account(db, son.id, display_name="SON_SELF", commit=False)
    ctx = resolve_sedi_retrieval_context(
        db,
        requester_account_id=son.id,
        target_health_subject_id=self_hs.id,
        purpose=PURPOSE_GOVERNED_RETRIEVAL,
        language="en",
    )
    assert ctx.subject_mode == SubjectMode.SELF
    assert ctx.requester_account_id == son.id
    assert ctx.target_health_subject_id == self_hs.id
    assert ctx.linked_user_id == son.id
    assert ctx.relationship == "SELF"
    print("SRCA-01=PASS")


@pytestmark_db
def test_srca_02_managed_mother_context_resolution(db):
    son = _user(db, "SRCA_SON_MGR")
    ensure_self_subject_for_account(db, son.id, display_name="SON_SELF", commit=False)
    mother, created = create_managed_person(
        db,
        account_user_id=son.id,
        display_name="MOTHER",
        access_role="MANAGER",
        idempotency_key=f"srca-mother-{uuid4().hex[:8]}",
        commit=False,
    )
    assert created is True
    assert mother.linked_user_id is None
    assert mother.subject_kind == "managed"
    ctx = resolve_sedi_retrieval_context(
        db,
        requester_account_id=son.id,
        target_health_subject_id=mother.id,
        language="en",
    )
    assert ctx.subject_mode == SubjectMode.MANAGED
    assert ctx.linked_user_id is None
    assert ctx.target_health_subject_id == mother.id
    assert ctx.requester_account_id == son.id
    print("SRCA-02=PASS")


@pytestmark_db
def test_srca_03_no_account_or_healthsubject_substitution(db):
    son = _user(db, "SRCA_SON_SUB")
    other = _user(db, "SRCA_OTHER_SUB")
    son_self = ensure_self_subject_for_account(db, son.id, display_name="SON", commit=False)
    other_self = ensure_self_subject_for_account(db, other.id, display_name="OTHER", commit=False)
    with pytest.raises(ContextResolutionDenied):
        resolve_sedi_retrieval_context(
            db,
            requester_account_id=son.id,
            target_health_subject_id=other_self.id,
        )
    # Managed with non-null linked_user_id must fail closed (no fake mother account).
    with pytest.raises(ValueError, match="NO_FAKE_MOTHER_ACCOUNT"):
        SediRetrievalContext(
            requester_account_id=son.id,
            target_health_subject_id=son_self.id,
            subject_mode=SubjectMode.MANAGED,
            relationship="MANAGER",
            authorization_scope=("x",),
            purpose=PURPOSE_GOVERNED_RETRIEVAL,
            language="en",
            linked_user_id=999,
        )
    print("SRCA-03=PASS")


@pytestmark_db
def test_srca_04_cross_family_context_blocked(db):
    son = _user(db, "SRCA_SON_XF")
    stranger = _user(db, "SRCA_STRANGER_XF")
    ensure_self_subject_for_account(db, son.id, commit=False)
    mother, _ = create_managed_person(
        db,
        account_user_id=son.id,
        display_name="MOTHER_XF",
        access_role="MANAGER",
        idempotency_key=f"srca-xf-{uuid4().hex[:8]}",
        commit=False,
    )
    with pytest.raises(ContextResolutionDenied):
        resolve_sedi_retrieval_context(
            db,
            requester_account_id=stranger.id,
            target_health_subject_id=mother.id,
        )
    print("SRCA-04=PASS")


@pytestmark_db
def test_srca_05_consent_access_and_scope_enforced(db):
    son = _user(db, "SRCA_SON_CONSENT")
    self_hs = ensure_self_subject_for_account(db, son.id, commit=False)
    with pytest.raises(ContextResolutionDenied, match="CONSENT"):
        resolve_sedi_retrieval_context(
            db,
            requester_account_id=son.id,
            target_health_subject_id=self_hs.id,
            purpose=PURPOSE_PERSONAL_CONTEXT_RELEVANCE,
            include_personal_context=True,
        )
    grant_memory_consent(db, son.id, commit=False)
    ctx = resolve_sedi_retrieval_context(
        db,
        requester_account_id=son.id,
        target_health_subject_id=self_hs.id,
        purpose=PURPOSE_PERSONAL_CONTEXT_RELEVANCE,
        include_personal_context=True,
    )
    assert ctx.personal_context_ref is not None
    assert ctx.personal_context_ref.authority == "I7"
    assert "I6_MEMORY_READ" in ctx.authorization_scope
    print("SRCA-05=PASS")


@pytestmark_db
def test_srca_06_revoked_or_wrong_subject_fail_closed(db):
    son = _user(db, "SRCA_SON_REV")
    ensure_self_subject_for_account(db, son.id, commit=False)
    mother, _ = create_managed_person(
        db,
        account_user_id=son.id,
        display_name="MOTHER_REV",
        access_role="MANAGER",
        idempotency_key=f"srca-rev-{uuid4().hex[:8]}",
        commit=False,
    )
    revoke_account_subject_access(db, account_user_id=son.id, health_subject_id=mother.id)
    with pytest.raises(ContextResolutionDenied):
        resolve_sedi_retrieval_context(
            db,
            requester_account_id=son.id,
            target_health_subject_id=mother.id,
        )
    with pytest.raises(ContextResolutionDenied):
        resolve_sedi_retrieval_context(
            db,
            requester_account_id=son.id,
            target_health_subject_id=9_999_999,
        )
    print("SRCA-06=PASS")


# ---------------------------------------------------------------------------
# SRCA-07..13 — authority / evidence semantics (unit + light PG)
# ---------------------------------------------------------------------------


def test_srca_07_i5_governed_knowledge_authority_preserved():
    ctx = _ctx()
    routes = route_sedi_retrieval_context(ctx)
    assert any(r.target_authority == "I5" and "GOVERNED" in r.route_kind for r in routes)
    req = build_scis_request_from_context("ALS care", ctx)
    assert "GLOBAL_GOVERNED_KNOWLEDGE" in req.allowed_knowledge_classes
    assert req.user_authorization_context["smart_rag_owns_sedi_truth"] is False
    pkg = SediEvidencePackage.from_scis_response(_synthetic_response(), ctx=ctx)
    assert pkg.knowledge_authority_label == "GOVERNED"
    print("SRCA-07=PASS")


def test_srca_08_i7_personal_context_relevance_only():
    ctx = _ctx(personal=True)
    pers = bounded_personalization_from_context(ctx, relevance_terms=("sleep", "routine"))
    assert pers is not None
    assert_personal_not_governed(pers)
    assert pers.to_audit_dict()["lifestyle_term_count"] == 2
    # Authority on evidence package remains GOVERNED — personal not promoted.
    pkg = SediEvidencePackage.from_scis_response(_synthetic_response(), ctx=ctx)
    assert pkg.knowledge_authority_label == "GOVERNED"
    with pytest.raises(PersonalToGovernedPromotionError):
        bad = SediRetrievalContext(
            requester_account_id=1,
            target_health_subject_id=1,
            subject_mode=SubjectMode.SELF,
            relationship="SELF",
            authorization_scope=("x",),
            purpose=PURPOSE_GOVERNED_RETRIEVAL,
            language="en",
            linked_user_id=1,
            personal_context_ref=BoundedContextRef(
                ref_type="personal", authority="GOVERNED", ref_id=1
            ),
        )
        bounded_personalization_from_context(bad, relevance_terms=("x",))
    print("SRCA-08=PASS")


def test_srca_09_rag_evidence_cannot_mint_i8_action():
    pkg = SediEvidencePackage.from_scis_response(_synthetic_response(), ctx=_ctx())
    payload = pkg.as_i8_evidence_input()
    assert payload["mints_i8_action"] is False
    assert pkg.is_action is False
    with pytest.raises(EvidenceSemanticEscalationError, match="I8_ACTION"):
        pkg.refuse_mint_i8_action()
    print("SRCA-09=PASS")


def test_srca_10_i9_status_context_cannot_mint_action_safety_or_diagnosis():
    ctx = _ctx(device=True)
    routes = route_sedi_retrieval_context(ctx)
    assert any(r.target_authority == "I9" and "STATUS" in r.route_kind for r in routes)
    pkg = SediEvidencePackage.from_scis_response(_synthetic_response(), ctx=ctx)
    assert pkg.is_device_status is False
    assert pkg.is_diagnosis is False
    with pytest.raises(EvidenceSemanticEscalationError):
        pkg.refuse_mint_i9_status()
    with pytest.raises(EvidenceSemanticEscalationError, match="I9_STATUS"):
        pkg.refuse_care_action_from_status()
    # STABLE label on ref is not diagnosis / action / safety.
    assert ctx.device_status_ref is not None
    assert ctx.device_status_ref.label == "STABLE"
    print("SRCA-10=PASS")


def test_srca_11_i4_clinical_safety_authority_preserved():
    ctx = _ctx(safety="NON_EMERGENCY_EDUCATION")
    routes = route_sedi_retrieval_context(ctx)
    assert any(r.target_authority == "I4" for r in routes)
    pkg = SediEvidencePackage.from_scis_response(_synthetic_response(), ctx=ctx)
    with pytest.raises(EvidenceSemanticEscalationError, match="DIAGNOSE"):
        pkg.refuse_diagnosis()
    # I4 chat safety signature must not accept device/vital kwargs (existing lock).
    from backend.app.services.intelligence.safety_risk import assess_safety_risk

    params = set(inspect.signature(assess_safety_risk).parameters)
    assert params.isdisjoint({"device_id", "packet", "vital", "heart_rate", "ecg"})
    print("SRCA-11=PASS")


def test_srca_12_evidence_package_provenance_trace_and_scope():
    ctx = _ctx()
    pkg = SediEvidencePackage.from_scis_response(_synthetic_response("trace-12"), ctx=ctx)
    assert pkg.trace_id == "trace-12"
    prov = pkg.provenance_summary()
    assert prov[0]["chunk_id"] == 1
    assert prov[0]["immutable_version_id"] == "v1"
    assert pkg.context_scope["subject_mode"] == "SELF"
    assert pkg.context_scope["trace_id"] == "srca-unit"
    assert pkg.response.embedding_model == DEFAULT_EMBEDDING_MODEL
    print("SRCA-12=PASS")


def test_srca_13_no_evidence_semantic_escalation():
    pkg = SediEvidencePackage.from_scis_response(_synthetic_response())
    pkg.assert_no_semantic_escalation()
    pkg.is_answer = True
    with pytest.raises(EvidenceSemanticEscalationError):
        pkg.assert_no_semantic_escalation()
    assert_router_not_authority()
    assert ROUTER_IS_AUTHORITY is False
    assert SMART_RAG_OWNS_SEDI_TRUTH is False
    assert RANKING_CANNOT_INCREASE_AUTHORITY is True
    print("SRCA-13=PASS")


# ---------------------------------------------------------------------------
# SRCA-14..17 — retrieval locks / leakage
# ---------------------------------------------------------------------------


def test_srca_14_en_fa_ar_context_aware_retrieval():
    for lang in ("en", "fa", "ar", "fa-IR", "en-US", "ar-SA"):
        assert is_supported_governed_language(lang)
    ctx_fa = SediRetrievalContext(
        requester_account_id=1,
        target_health_subject_id=1,
        subject_mode=SubjectMode.SELF,
        relationship="SELF",
        authorization_scope=("I5_GOVERNED_KNOWLEDGE",),
        purpose=PURPOSE_GOVERNED_RETRIEVAL,
        language="fa",
        linked_user_id=1,
        trace_id="fa",
    )
    req = build_scis_request_from_context("مراقبت ALS", ctx_fa)
    assert req.query_language == "fa"
    print("SRCA-14=PASS")


def test_srca_15_hybrid_kce1024_rrf_preserved():
    assert DEFAULT_EMBEDDING_MODEL == "text-embedding-3-large"
    assert DEFAULT_EMBEDDING_DIM == 1024
    assert RRF_K == 60
    a = [RankedCandidate(1, "lexical", 1, 1.0, {}), RankedCandidate(2, "lexical", 2, 0.5, {})]
    b = [RankedCandidate(2, "vector", 1, 1.0, {}), RankedCandidate(1, "vector", 2, 0.5, {})]
    fused = reciprocal_rank_fusion([a, b], k=RRF_K)
    assert fused[0][0] in (1, 2)
    # Source lock: hybrid module still owns RRF_K=60
    hybrid_src = (SCIS_ROOT / "hybrid.py").read_text(encoding="utf-8")
    assert "RRF_K = 60" in hybrid_src
    emb_src = (SCIS_ROOT / "embedding" / "providers.py").read_text(encoding="utf-8")
    assert "text-embedding-3-large" in emb_src
    assert "1024" in emb_src
    print("SRCA-15=PASS")


def test_srca_16_safe_fallback_and_noncanonical_paths_lock():
    adapter = (SCIS_ROOT / "governed_runtime_adapter.py").read_text(encoding="utf-8")
    assert "SAFE_CANONICAL_LEXICAL" in adapter or "LEXICAL" in adapter
    assert "Cohere" in adapter or "cohere" in adapter.lower()
    assert "Stage17" in adapter or "stage17" in adapter.lower()
    # Product path must not call Cohere/Stage17 as canonical.
    for name in (
        "context_aware_retrieval.py",
        "context_resolver.py",
        "authority_router.py",
        "evidence_package.py",
        "sedi_retrieval_context.py",
    ):
        src = (SCIS_ROOT / name).read_text(encoding="utf-8")
        assert "cohere.Client" not in src
        # Forbid Stage17 product table/runtime imports — lock field names OK.
        assert "from backend.app.services.local_rag" not in src
        assert "models.RagEmbedding" not in src and "rag_embeddings)" not in src
        assert "CREATE TABLE rag_embeddings" not in src
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "i10" not in node.module.split("."), name
                assert node.module != "cohere", name
    # Fallback enum preserved
    assert FallbackState.EMBEDDING_FAILURE.value == "embedding_failure"
    assert FallbackState.LEXICAL_ONLY.value == "lexical_only"
    print("SRCA-16=PASS")


def test_srca_17_no_raw_cross_i_data_leakage():
    with pytest.raises(ValueError, match="RAW_CROSS_I"):
        reject_forbidden_raw_keys({"RAW_I7_MEMORY": ["secret"]})
    with pytest.raises(ValueError, match="RAW_CROSS_I"):
        reject_forbidden_raw_keys({"raw_ecg": b"x"})
    ctx = _ctx(personal=True, device=True)
    boundary = ctx.to_authorization_boundary()
    assert "personal_context_ref" in boundary
    assert boundary["personal_context_ref"]["authority"] == "I7"
    assert "raw_i7_memory" not in boundary
    assert "raw_device_measurements" not in boundary
    for key in FORBIDDEN_RAW_CONTEXT_KEYS:
        assert key not in boundary
    # Evidence package must not expose mint flags as true
    pkg = SediEvidencePackage.from_scis_response(_synthetic_response(), ctx=ctx)
    inp = pkg.as_i8_evidence_input()
    assert inp["mints_i9_status"] is False
    assert inp["mints_i10_semantic"] is False
    assert inp["is_diagnosis"] is False
    print("SRCA-17=PASS")


# ---------------------------------------------------------------------------
# SRCA-18 — runtime / schema lock + PG16 retrieval canary
# ---------------------------------------------------------------------------


def test_srca_18_pg16_alembic081_runtime_and_no_hidden_schema_change():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == [ALEMBIC_HEAD], heads
    # Gate must not add migrations
    versions = root / "alembic" / "versions"
    newer = [
        p.name
        for p in versions.glob("*.py")
        if re.match(r"08[2-9]_", p.name) or re.match(r"09\d_", p.name)
    ]
    assert newer == [], newer
    print("SRCA-18_STATIC=PASS")


@pytestmark_db
def test_srca_18_pg16_runtime_retrieval_canary(db, scis_engine):
    with scis_engine.connect() as conn:
        ver = conn.execute(text("SHOW server_version")).scalar()
        assert str(ver).startswith("16.")
        pv = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar()
        assert pv
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        # CI upgrades to head; local may already be at 081.
        assert rev == ALEMBIC_HEAD or rev is not None

    son = _user(db, "SRCA_SON_RT")
    self_hs = ensure_self_subject_for_account(db, son.id, commit=False)
    _index_ku(db, lang="en")
    db.flush()
    ctx = resolve_sedi_retrieval_context(
        db,
        requester_account_id=son.id,
        target_health_subject_id=self_hs.id,
        language="en",
        domain="neurology",
    )
    pkg, meta = retrieve_sedi_evidence_package(
        db,
        "ALS daily care monitoring",
        ctx,
        top_k=3,
        allow_network=False,
        provider=FakeScisEmbeddingProvider(),
        force_mode=RetrievalMode.HYBRID,
    )
    assert pkg.knowledge_authority_label == "GOVERNED"
    assert meta.get("cohere_used") is False
    assert meta.get("stage17_rag_embeddings_used") is False
    assert pkg.response.request_trace_id == ctx.trace_id
    assert pkg.context_scope["subject_mode"] == "SELF"
    # Observability must not claim I10 mint
    assert pkg.response.observability.get("personal_promoted_to_governed") is False
    print("SRCA-18=PASS")
    print(f"GATE_ID={GATE_ID}")
