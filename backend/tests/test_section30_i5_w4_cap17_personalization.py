"""Section 30 / CAP-OPEN-17 — safe personalization relevance on W4-P01 retrieval.

Personalization is post-eligibility ranking only. No schema/migration. No PHI
persistence onto shared KU/Memory rows. Runtime selectors owned by
w4p01-cap17-personalization-runtime.yml.
"""
from __future__ import annotations

import importlib
from typing import Any

import pytest
from sqlalchemy.orm import configure_mappers

from backend.app.services.i5.runtime_knowledge_retrieval import (
    PACKAGE_ID,
    STATUS_NO_ELIGIBLE_KNOWLEDGE,
    STATUS_OK,
    RetrievalPersonalizationContext,
    assert_no_base_model_medical_fallback,
    build_personalization_context_from_memory,
    normalize_personalization_context,
    retrieve_knowledge_context,
)
from backend.tests.test_section30_i5_w4_p01_runtime_kb_first import (
    _det_hex,
    _ensure_ku,
    _ensure_memory,
    _ensure_provenance,
    _require_postgres,
    _seed_eligible,
)


def _load_models():
    return importlib.import_module("backend.app.models")


def test_P17_T01_baseline_empty_personalization(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(db, normalized_statement="Migraine prevention lifestyle guidance")
    baseline = retrieve_knowledge_context(
        db, "migraine prevention", language="en", enqueue_gap_on_empty=False
    )
    empty = retrieve_knowledge_context(
        db,
        "migraine prevention",
        language="en",
        enqueue_gap_on_empty=False,
        personalization=None,
    )
    zero = retrieve_knowledge_context(
        db,
        "migraine prevention",
        language="en",
        enqueue_gap_on_empty=False,
        personalization=RetrievalPersonalizationContext(),
    )
    assert baseline.status == STATUS_OK
    assert empty.status == STATUS_OK
    assert zero.personalization_applied is False
    assert [i.knowledge_unit_id for i in baseline.items] == [
        i.knowledge_unit_id for i in empty.items
    ]
    assert [i.knowledge_unit_id for i in baseline.items] == [
        i.knowledge_unit_id for i in zero.items
    ]
    assert [i.rank_score for i in baseline.items] == [i.rank_score for i in empty.items]


def test_P17_T02_goal_relevance_ranking(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        evidence_strength="MODERATE",
        canonical_unit_id="canon-sleep-hygiene",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Adult sleep hygiene habits for restorative rest",
    )
    _seed_eligible(
        db,
        evidence_strength="MODERATE",
        canonical_unit_id="canon-sleep-general",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Adult sleep duration educational overview",
    )
    pers = RetrievalPersonalizationContext(goal_terms=("hygiene", "restorative"))
    result = retrieve_knowledge_context(
        db,
        "sleep adult",
        language="en",
        domain="lifestyle",
        limit=2,
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert result.status == STATUS_OK
    assert len(result.items) == 2
    assert result.personalization_applied is True
    assert result.items[0].canonical_unit_id == "canon-sleep-hygiene"
    assert result.items[0].personalization_score > result.items[1].personalization_score
    assert "goal_relevance" in result.items[0].personalization_reasons


def test_P17_T03_query_relevance_precedes_personalization(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        evidence_strength="HIGH",
        canonical_unit_id="canon-query-hit",
        topic_taxonomy="migraine",
        domain="neurology",
        normalized_statement="Migraine prevention lifestyle guidance for adults",
    )
    _seed_eligible(
        db,
        evidence_strength="HIGH",
        canonical_unit_id="canon-pers-only",
        topic_taxonomy="nutrition",
        domain="neurology",
        normalized_statement="Hydration lifestyle guidance for adults",
    )
    pers = RetrievalPersonalizationContext(goal_terms=("hydration", "lifestyle"))
    result = retrieve_knowledge_context(
        db,
        "migraine prevention",
        language="en",
        domain="neurology",
        limit=2,
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    ids = {i.canonical_unit_id for i in result.items}
    assert "canon-query-hit" in ids
    assert "canon-pers-only" not in ids
    assert any(e.reason == "QUERY_NO_MATCH" for e in result.exclusions)


def test_P17_T04_safety_precedence_not_eligible(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        medical_safety_state="PENDING_REVIEW",
        runtime_eligibility="REVIEW_REQUIRED",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Pending review sleep hygiene guidance",
        memory_overrides={"runtime_eligibility": "ELIGIBLE"},
    )
    pers = RetrievalPersonalizationContext(goal_terms=("sleep", "hygiene"))
    result = retrieve_knowledge_context(
        db,
        "sleep hygiene",
        language="en",
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert result.items == []
    assert any("KU_NOT_ELIGIBLE" in e.reason for e in result.exclusions)


def test_P17_T05_provenance_precedence(db):
    _require_postgres(db)
    configure_mappers()
    ku = _ensure_ku(
        db,
        provenance_complete=True,
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Sleep hygiene without provenance row",
    )
    _ensure_memory(db, ku)
    pers = RetrievalPersonalizationContext(goal_terms=("sleep", "hygiene"))
    result = retrieve_knowledge_context(
        db,
        "sleep hygiene",
        language="en",
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert result.items == []
    assert any(e.reason == "MISSING_PROVENANCE_ROW" for e in result.exclusions)


def test_P17_T06_superseded_not_selected(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        publication_state="SUPERSEDED",
        runtime_eligibility="NOT_ELIGIBLE",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Superseded sleep hygiene guidance",
    )
    pers = RetrievalPersonalizationContext(goal_terms=("sleep", "hygiene"))
    result = retrieve_knowledge_context(
        db,
        "sleep hygiene",
        language="en",
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert result.items == []


def test_P17_T07_language_personalization_soft_boost(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        language="en",
        evidence_strength="MODERATE",
        canonical_unit_id="canon-en-sleep",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Sleep hygiene educational note english",
    )
    _seed_eligible(
        db,
        language="fa",
        evidence_strength="MODERATE",
        canonical_unit_id="canon-fa-sleep",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Sleep hygiene educational note persian",
    )
    pers = RetrievalPersonalizationContext(language="fa", goal_terms=("sleep",))
    result = retrieve_knowledge_context(
        db,
        "sleep hygiene",
        language=None,
        domain="lifestyle",
        limit=2,
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert len(result.items) == 2
    assert result.items[0].language == "fa"
    assert "language_match" in result.items[0].personalization_reasons


def test_P17_T08_restriction_relevance_metadata(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        evidence_strength="MODERATE",
        canonical_unit_id="canon-caffeine",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Reduce evening caffeine for better sleep",
    )
    _seed_eligible(
        db,
        evidence_strength="MODERATE",
        canonical_unit_id="canon-generic-sleep",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="General sleep duration educational overview",
    )
    pers = RetrievalPersonalizationContext(restriction_terms=("caffeine",))
    result = retrieve_knowledge_context(
        db,
        "sleep",
        language="en",
        domain="lifestyle",
        limit=2,
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert result.items[0].canonical_unit_id == "canon-caffeine"
    assert "restriction_relevance" in result.items[0].personalization_reasons
    # Reasons must not embed raw user values.
    joined = " ".join(result.items[0].personalization_reasons)
    assert "avoid" not in joined


def test_P17_T09_cross_user_isolation(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        evidence_strength="MODERATE",
        canonical_unit_id="canon-shared-sleep",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Sleep hygiene and caffeine timing guidance",
    )
    pers_a = RetrievalPersonalizationContext(goal_terms=("caffeine",))
    pers_b = RetrievalPersonalizationContext(goal_terms=("unrelatedxyz",))
    a = retrieve_knowledge_context(
        db,
        "sleep",
        user_id=101,
        language="en",
        domain="lifestyle",
        enqueue_gap_on_empty=False,
        personalization=pers_a,
    )
    b = retrieve_knowledge_context(
        db,
        "sleep",
        user_id=202,
        language="en",
        domain="lifestyle",
        enqueue_gap_on_empty=False,
        personalization=pers_b,
    )
    assert a.items[0].personalization_score > b.items[0].personalization_score
    assert a.user_id_scope == 101
    assert b.user_id_scope == 202
    # Shared KU row must not store user-specific personalization fields.
    models = _load_models()
    ku = (
        db.query(models.KnowledgeUnit)
        .filter(models.KnowledgeUnit.canonical_unit_id == "canon-shared-sleep")
        .one()
    )
    ku_cols = {c.name for c in ku.__table__.columns}
    assert "user_id" not in ku_cols
    assert "goal_terms" not in ku_cols
    assert "personalization" not in "|".join(ku_cols)


def test_P17_T10_no_user_phi_on_shared_knowledge(db):
    _require_postgres(db)
    configure_mappers()
    gsp, ku, mem, prov = _seed_eligible(
        db,
        normalized_statement="Sleep hygiene educational overview",
        topic_taxonomy="sleep",
        domain="lifestyle",
    )
    secret_goal = "private-goal-token-" + _det_hex(4)
    pers = RetrievalPersonalizationContext(goal_terms=(secret_goal, "sleep"))
    result = retrieve_knowledge_context(
        db,
        "sleep hygiene",
        user_id=777,
        language="en",
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert result.status == STATUS_OK
    models = _load_models()
    db.refresh(ku)
    db.refresh(mem)
    db.refresh(prov)
    for row in (ku, mem, prov, gsp):
        blob = " ".join(str(getattr(row, c.name, "")) for c in row.__table__.columns)
        assert secret_goal not in blob


def test_P17_T11_no_base_model_fallback(db):
    _require_postgres(db)
    configure_mappers()
    pers = RetrievalPersonalizationContext(goal_terms=("migraine", "sleep"))
    result = retrieve_knowledge_context(
        db,
        "completely unknown xyzzy disease",
        language="en",
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert result.status == STATUS_NO_ELIGIBLE_KNOWLEDGE
    assert result.items == []
    assert_no_base_model_medical_fallback(result)


def test_P17_T12_care_context_personalization_wiring(db):
    _require_postgres(db)
    configure_mappers()
    models = _load_models()
    user = models.User(name=f"cap17-{_det_hex(4)}", secret_key="k")
    db.add(user)
    db.flush()
    from datetime import datetime

    now = datetime.utcnow()
    goal = models.UserGoal(
        user_id=user.id,
        category="lifestyle",
        title="Improve sleep hygiene",
        description=None,
        status="active",
        source="test",
        created_at=now,
        updated_at=now,
    )
    db.add(goal)
    db.flush()
    _seed_eligible(
        db,
        language="fa",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Sleep hygiene educational guidance fa",
    )
    from backend.app.services.gate3.care_intelligence import build_care_context

    ctx = build_care_context(db, user.id, language="fa", query_hint="sleep hygiene")
    assert ctx.get("knowledge_db_first_package") == PACKAGE_ID
    assert "personalization_applied" in ctx
    assert "personalization_audit" in ctx
    audit = ctx["personalization_audit"]
    assert isinstance(audit, dict)
    assert "goal_term_count" in audit
    # Raw goal title must not appear in audit payload.
    assert "Improve sleep hygiene" not in str(audit)
    assert "Improve sleep hygiene" not in str(ctx.get("i5_knowledge_retrieval") or {})


def test_P17_T13_w4p02_handoff_compatibility(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        normalized_statement="Migraine prevention lifestyle guidance",
    )
    pers = RetrievalPersonalizationContext(goal_terms=("migraine",))
    result = retrieve_knowledge_context(
        db,
        "migraine prevention",
        language="en",
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert result.status == STATUS_OK
    handoff = result.items[0].w4p02_handoff()
    assert handoff["render_owned_by"] == "I5-IMPL-W4-P02"
    assert handoff["provenance_id"] == result.items[0].provenance_id
    snippet = result.items[0].as_care_snippet()
    assert "citation" in snippet
    assert snippet["citation"]["handoff"] == "W4-P02"


def test_P17_T14_determinism(db):
    _require_postgres(db)
    configure_mappers()
    _seed_eligible(
        db,
        evidence_strength="MODERATE",
        canonical_unit_id="canon-det-a",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Sleep hygiene restorative rest guidance",
    )
    _seed_eligible(
        db,
        evidence_strength="MODERATE",
        canonical_unit_id="canon-det-b",
        topic_taxonomy="sleep",
        domain="lifestyle",
        normalized_statement="Sleep duration educational overview",
    )
    pers = RetrievalPersonalizationContext(goal_terms=("hygiene", "restorative"))
    r1 = retrieve_knowledge_context(
        db,
        "sleep",
        language="en",
        domain="lifestyle",
        limit=2,
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    r2 = retrieve_knowledge_context(
        db,
        "sleep",
        language="en",
        domain="lifestyle",
        limit=2,
        enqueue_gap_on_empty=False,
        personalization=pers,
    )
    assert [i.canonical_unit_id for i in r1.items] == [
        i.canonical_unit_id for i in r2.items
    ]
    assert [i.rank_score for i in r1.items] == [i.rank_score for i in r2.items]


def test_P17_T00_malformed_personalization_degrades():
    assert normalize_personalization_context({"goal_terms": object()}) is None
    assert normalize_personalization_context({"goal_terms": [object(), ""]}) is None
    built = build_personalization_context_from_memory(
        {
            "goals": [{"title": "Better sleep"}],
            "medications": ["secret-drug"],
            "conditions": ["secret-condition"],
            "doctors": [{"phone": "555-0100"}],
        },
        language="en",
    )
    assert built is not None
    assert "sleep" in built.goal_terms
    blob = " ".join(built.goal_terms + built.lifestyle_terms + built.restriction_terms)
    assert "secret-drug" not in blob
    assert "secret-condition" not in blob
    assert "555-0100" not in blob
