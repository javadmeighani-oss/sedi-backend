"""Section 30 / W4-P01 — Knowledge-Database-First runtime retrieval (P08).

Runtime selectors are exercised by w4p01-postgresql-knowledge-retrieval-runtime.yml.
Synthesis / reference rendering are NOT owned (W4-P02). No live network / activation.
"""
from __future__ import annotations

import importlib
from typing import Any

import pytest
from sqlalchemy.orm import configure_mappers

from backend.app.services.i5 import runtime_knowledge_retrieval as rkr
from backend.app.services.i5.runtime_knowledge_retrieval import (
    MANAGEMENT_ALIAS,
    PACKAGE_ID,
    SERVICE_NAME,
    STATUS_NO_ELIGIBLE_KNOWLEDGE,
    STATUS_OK,
    assert_no_base_model_medical_fallback,
    normalize_query,
    retrieve_knowledge_context,
)


def _load_models():
    return importlib.import_module("backend.app.models")


def _require_postgres(db) -> None:
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("PostgreSQL required for this invariant (CI-gated)")


_DET_SEQ = 0


def _det_hex(nbytes: int = 32) -> str:
    global _DET_SEQ
    _DET_SEQ += 1
    return f"{_DET_SEQ:0{nbytes * 2}x}"[-nbytes * 2 :]


def _build_gsp(**overrides):
    models = _load_models()
    base = dict(
        canonical_key="w4p01-gsp-" + _det_hex(8),
        operational_status="ACTIVE",
        registry_state="ACTIVE",
        runtime_eligibility="NOT_ELIGIBLE",
        canonicalization_version="v1",
    )
    base.update(overrides)
    return models.GovernedSourceProfile(**base)


def _eligible_ku_kwargs(**overrides) -> dict[str, Any]:
    base = dict(
        provenance_complete=True,
        evidence_strength="HIGH",
        freshness_state="CURRENT",
        conflict_state="NONE",
        medical_safety_state="CLEARED",
        publication_state="PUBLISHED",
        runtime_eligibility="ELIGIBLE",
        retraction_reason=None,
        topic_taxonomy="migraine",
        domain="neurology",
        language="en",
        knowledge_type="FACT",
        normalized_statement="Migraine prevention lifestyle guidance for adults",
    )
    base.update(overrides)
    return base


def _build_ku(**overrides):
    models = _load_models()
    kwargs = _eligible_ku_kwargs(**overrides)
    stmt = kwargs.pop("normalized_statement")
    dedupe = kwargs.pop("deduplication_key", None) or _det_hex(32)
    canon = kwargs.pop("canonical_hash", None) or _det_hex(32)
    base = dict(
        canonical_unit_id=kwargs.pop("canonical_unit_id", "ku-" + _det_hex(8)),
        immutable_version_id=kwargs.pop("immutable_version_id", "v-" + _det_hex(8)),
        normalized_statement=stmt,
        deduplication_key=dedupe,
        canonical_hash=canon,
        hash_algorithm="SHA-256",
        canonicalization_version="v1",
    )
    base.update(kwargs)
    return models.KnowledgeUnit(**base)


def _ensure_gsp(db, **overrides):
    gsp = _build_gsp(**overrides)
    db.add(gsp)
    db.flush()
    return gsp


def _ensure_ku(db, **overrides):
    ku = _build_ku(**overrides)
    db.add(ku)
    db.flush()
    return ku


def _ensure_memory(db, ku, **overrides):
    models = _load_models()
    mid = overrides.pop("memory_item_id", None) or _det_hex(32)
    base = dict(
        memory_item_id=mid,
        knowledge_unit_id=ku.id,
        domain=ku.domain,
        topic=ku.topic_taxonomy or "migraine",
        knowledge_version=ku.immutable_version_id,
        evidence_strength=ku.evidence_strength,
        freshness_state=ku.freshness_state,
        conflict_state=ku.conflict_state,
        medical_safety_state=ku.medical_safety_state,
        runtime_eligibility=ku.runtime_eligibility,
        supersession_state="CURRENT",
    )
    base.update(overrides)
    mem = models.KnowledgeMemoryItem(**base)
    db.add(mem)
    db.flush()
    return mem


def _ensure_provenance(db, ku, gsp=None, **overrides):
    models = _load_models()
    if gsp is None:
        gsp = _ensure_gsp(db)
    base = dict(
        knowledge_unit_id=ku.id,
        source_profile_id=gsp.id,
        retrieval_method="W4P01_TEST_FIXTURE",
    )
    base.update(overrides)
    row = models.KnowledgeProvenance(**base)
    db.add(row)
    db.flush()
    return row


def _seed_eligible(db, *, memory_overrides: dict[str, Any] | None = None, **ku_overrides):
    gsp = _ensure_gsp(db)
    ku = _ensure_ku(db, **ku_overrides)
    mem = _ensure_memory(db, ku, **(memory_overrides or {}))
    prov = _ensure_provenance(db, ku, gsp=gsp)
    return gsp, ku, mem, prov


def test_W4P01_T1_package_identity():
    assert PACKAGE_ID == "I5-IMPL-W4-P01"
    assert MANAGEMENT_ALIAS == "P08"
    assert SERVICE_NAME == "runtime_knowledge_retrieval"
    assert rkr.DEFAULT_LIMIT == 3
    assert rkr.MAX_LIMIT == 10
    assert rkr.NO_BASE_MODEL_FALLBACK is True


def test_W4P01_T2_query_normalization():
    nq = normalize_query("  Migraine,  PREVENTION!!  ")
    assert nq.original_query == "  Migraine,  PREVENTION!!  "
    assert "migraine" in nq.normalized_query
    assert "prevention" in nq.normalized_query
    assert "," not in nq.normalized_query
    assert nq.tokens[0] == "migraine"


def test_W4P01_T3_eligible_current_returned(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(db, normalized_statement="Migraine prevention lifestyle guidance")
    result = retrieve_knowledge_context(
        db, "migraine prevention", language="en", domain="neurology", enqueue_gap_on_empty=False
    )
    assert result.status == STATUS_OK
    assert len(result.items) == 1
    assert result.items[0].runtime_eligibility == "ELIGIBLE"
    assert result.no_base_model_fallback is True


def test_W4P01_T4_superseded_excluded(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        publication_state="SUPERSEDED",
        runtime_eligibility="NOT_ELIGIBLE",
        normalized_statement="Old migraine statement superseded",
    )
    result = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    assert len(result.items) == 0
    reasons = {e.reason for e in result.exclusions}
    assert any(
        r.startswith("KU_NOT_ELIGIBLE")
        or r.startswith("PUBLICATION_")
        or "MEMORY_NOT_ELIGIBLE" in r
        for r in reasons
    )


def test_W4P01_T5_retracted_excluded(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        retraction_reason="withdrawn by source",
        runtime_eligibility="REVOKED",
        normalized_statement="Retracted migraine claim",
    )
    result = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    assert len(result.items) == 0
    assert any(
        "REVOKED" in e.reason or e.reason == "RETRACTED" for e in result.exclusions
    )


def test_W4P01_T6_missing_provenance_excluded(db):
    _require_postgres(db)
    configure_mappers()
    ku = _ensure_ku(
        db,
        provenance_complete=True,
        normalized_statement="Migraine without provenance row",
    )
    _ensure_memory(db, ku)
    result = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    assert len(result.items) == 0
    assert any(e.reason == "MISSING_PROVENANCE_ROW" for e in result.exclusions)


def test_W4P01_T7_stale_excluded(db):
    _require_postgres(db)
    configure_mappers()
    # Keep memory column ELIGIBLE so KU freshness matrix (not memory column) is exercised.
    _seed_eligible(
        db,
        freshness_state="STALE",
        runtime_eligibility="NOT_ELIGIBLE",
        normalized_statement="Stale migraine guidance",
        memory_overrides={"runtime_eligibility": "ELIGIBLE"},
    )
    result = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    assert len(result.items) == 0
    assert any("KU_NOT_ELIGIBLE" in e.reason for e in result.exclusions)


@pytest.mark.parametrize(
    "conflict_state,label",
    [("SUSPECTED", "suspected"), ("CONFIRMED", "confirmed")],
    ids=["suspected", "confirmed"],
)
def test_W4P01_T8_conflict_excluded(db, conflict_state: str, label: str):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        conflict_state=conflict_state,
        runtime_eligibility="REVIEW_REQUIRED",
        normalized_statement=f"Conflicted migraine {label}",
        memory_overrides={"runtime_eligibility": "ELIGIBLE"},
    )
    result = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    assert len(result.items) == 0
    assert any("KU_NOT_ELIGIBLE" in e.reason for e in result.exclusions)


@pytest.mark.parametrize(
    "safety,runtime_elig,label",
    [
        ("PENDING_REVIEW", "REVIEW_REQUIRED", "pending_review"),
        ("RESTRICTED", "NOT_ELIGIBLE", "restricted"),
        ("BLOCKED", "NOT_ELIGIBLE", "blocked"),
    ],
    ids=["pending_review", "restricted", "blocked"],
)
def test_W4P01_T9_medical_safety_excluded(
    db, safety: str, runtime_elig: str, label: str
):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        medical_safety_state=safety,
        runtime_eligibility=runtime_elig,
        normalized_statement=f"Safety {label} migraine note",
        memory_overrides={"runtime_eligibility": "ELIGIBLE"},
    )
    result = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    assert len(result.items) == 0
    assert any("KU_NOT_ELIGIBLE" in e.reason for e in result.exclusions)


def test_W4P01_T10_ranking_deterministic(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        evidence_strength="LOW",
        canonical_unit_id="canon-rank-low",
        normalized_statement="Migraine low evidence note",
    )
    _seed_eligible(
        db,
        evidence_strength="HIGH",
        canonical_unit_id="canon-rank-high",
        normalized_statement="Migraine high evidence note",
    )
    result = retrieve_knowledge_context(
        db, "migraine", language="en", limit=2, enqueue_gap_on_empty=False
    )
    assert result.status == STATUS_OK
    assert len(result.items) == 2
    assert result.items[0].evidence_strength == "HIGH"
    assert result.items[1].evidence_strength == "LOW"
    again = retrieve_knowledge_context(
        db, "migraine", language="en", limit=2, enqueue_gap_on_empty=False
    )
    assert [i.knowledge_unit_id for i in again.items] == [
        i.knowledge_unit_id for i in result.items
    ]


def test_W4P01_T11_no_safe_knowledge_gap_enqueue(db):
    _require_postgres(db)
    configure_mappers()
    result = retrieve_knowledge_context(
        db, "completely unknown xyzzy disease", language="en", enqueue_gap_on_empty=True
    )
    assert result.status == STATUS_NO_ELIGIBLE_KNOWLEDGE
    assert result.items == []
    assert result.gap_id is not None
    assert result.no_base_model_fallback is True
    models = _load_models()
    gap = db.query(models.KnowledgeGap).filter(models.KnowledgeGap.id == result.gap_id).one()
    assert gap.gap_type == "RUNTIME_RETRIEVAL_FAILURE"
    assert gap.target_package_id == PACKAGE_ID


def test_W4P01_T12_language_filter_personalization(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        language="en",
        normalized_statement="Migraine English guidance",
    )
    _seed_eligible(
        db,
        language="fa",
        canonical_unit_id="ku-fa-" + _det_hex(4),
        normalized_statement="Migraine Persian guidance",
    )
    en_only = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    assert all(i.language == "en" for i in en_only.items)
    assert len(en_only.items) == 1


def test_W4P01_T13_no_base_model_fallback_marker(db):
    _require_postgres(db)
    configure_mappers()
    result = retrieve_knowledge_context(
        db, "no match query", language="en", enqueue_gap_on_empty=False
    )
    assert_no_base_model_medical_fallback(result)
    assert result.no_base_model_fallback is True
    payload = result.to_dict()
    assert payload["no_base_model_fallback"] is True


def test_W4P01_T14_care_context_kb_first(db):
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    user = models.User(name=f"w4p01-{_det_hex(4)}", secret_key="k")
    db.add(user)
    db.flush()
    _seed_eligible(
        db,
        language="fa",
        normalized_statement="Migraine prevention lifestyle guidance fa",
    )
    from backend.app.services.gate3.care_intelligence import build_care_context

    ctx = build_care_context(db, user.id, language="fa", query_hint="migraine prevention")
    assert ctx.get("knowledge_db_first_package") == PACKAGE_ID
    assert ctx.get("no_base_model_fallback") is True
    assert "i5_knowledge_retrieval" in ctx
    assert ctx["i5_knowledge_retrieval"]["no_base_model_fallback"] is True
    assert "knowledge_snippets" in ctx


def test_W4P01_T15_multiple_current_fail_closed(db):
    _require_postgres(db)
    configure_mappers()
    canon = "shared-canon-" + _det_hex(4)
    gsp = _ensure_gsp(db)
    ku1 = _ensure_ku(
        db,
        canonical_unit_id=canon,
        immutable_version_id="v-a",
        normalized_statement="Migraine version A",
    )
    ku2 = _ensure_ku(
        db,
        canonical_unit_id=canon,
        immutable_version_id="v-b",
        normalized_statement="Migraine version B",
    )
    _ensure_memory(db, ku1)
    _ensure_memory(db, ku2)
    _ensure_provenance(db, ku1, gsp=gsp)
    _ensure_provenance(db, ku2, gsp=gsp)
    result = retrieve_knowledge_context(
        db, "migraine", language="en", enqueue_gap_on_empty=False
    )
    assert all(i.canonical_unit_id != canon for i in result.items)
    assert any(e.reason == "MULTIPLE_CURRENT_CANDIDATES" for e in result.exclusions)


def test_W4P01_T16_w4p02_handoff_fields(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(db, normalized_statement="Migraine prevention handoff note")
    result = retrieve_knowledge_context(
        db, "migraine prevention", language="en", enqueue_gap_on_empty=False
    )
    assert result.status == STATUS_OK
    handoff = result.items[0].w4p02_handoff()
    assert handoff["render_owned_by"] == "I5-IMPL-W4-P02"
    assert handoff["knowledge_unit_id"] == result.items[0].knowledge_unit_id
    assert handoff["provenance_id"] == result.items[0].provenance_id
    assert "normalized_statement" in handoff
