"""Phase2-A Smart-RAG deterministic query intelligence — focused unit proofs."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.i5.retrieval_sufficiency import (
    SUFFICIENCY_LOW_ONLY,
    SUFFICIENCY_NO_ELIGIBLE,
    SUFFICIENCY_OK,
    SUFFICIENCY_PERSONAL_HISTORY_BLOCKED,
    SUFFICIENCY_UNRESOLVED_CONFLICT,
    detect_retrieval_set_contradictions,
    evaluate_retrieval_sufficiency,
)
from backend.app.services.i5.runtime_knowledge_retrieval import (
    AUTHORITY_LABEL_GOVERNED,
    STATUS_INSUFFICIENT_CONTEXT,
    STATUS_OK,
    RetrievedKnowledgeItem,
    assert_no_base_model_medical_fallback,
    retrieve_knowledge_context,
)
from backend.app.services.scis.alias_expansion import (
    ALIAS_AUTHORITY,
    MAX_ALIAS_EXPANSIONS_PER_QUERY,
    AliasRegistry,
    expand_query_aliases,
    get_product_alias_registry,
)
from backend.app.services.scis.lexical_query import (
    MAX_PHRASE_TOKENS,
    MAX_PHRASES_PER_QUERY,
    extract_important_phrases,
    formulate_lexical_query_plan,
)
from backend.app.services.scis.temporal_query import (
    STATE_AMBIGUOUS,
    STATE_RESOLVED,
    parse_temporal_query_intent,
)


def _item(
    *,
    ku_id: int,
    canon: str,
    statement: str,
    strength: str = "MODERATE",
    domain: str = "lifestyle",
    topic: str = "sleep",
    conflict: str = "NONE",
) -> RetrievedKnowledgeItem:
    return RetrievedKnowledgeItem(
        knowledge_unit_id=ku_id,
        canonical_unit_id=canon,
        immutable_version_id=f"v{ku_id}",
        memory_item_id=f"SCIS_KCE:{ku_id}",
        memory_row_id=0,
        source_profile_id=1,
        provenance_id=1,
        raw_evidence_id=1,
        domain=domain,
        language="en",
        topic_taxonomy=topic,
        normalized_statement=statement,
        evidence_strength=strength,
        freshness_state="CURRENT",
        conflict_state=conflict,
        medical_safety_state="CLEARED",
        runtime_eligibility="ELIGIBLE",
        rank_score=100,
        inclusion_reasons=["GOVERNED", "SCIS_HYBRID"],
    )


# --- A. Phrase recognition ---


def test_phrase_en_blood_pressure_monitoring():
    plan = formulate_lexical_query_plan("tips for blood pressure monitoring", language="en")
    assert "blood pressure monitoring" in plan.phrases or "blood pressure" in plan.phrases
    assert plan.original_query == "tips for blood pressure monitoring"
    assert plan.primary_token_count <= 8


def test_phrase_fa_blood_pressure():
    plan = formulate_lexical_query_plan("راهنمای فشار خون", language="fa")
    assert any("فشار خون" in p or p == "فشار خون" for p in plan.phrases)
    assert plan.original_query == "راهنمای فشار خون"


def test_phrase_ar_blood_pressure():
    plan = formulate_lexical_query_plan("معلومات عن ضغط الدم", language="ar")
    assert any("ضغط الدم" in p or p == "ضغط الدم" for p in plan.phrases)


def test_phrase_bounds_enforced():
    tokens = tuple(f"tok{i}" for i in range(20))
    phrases = extract_important_phrases(tokens, language="en")
    assert len(phrases) <= MAX_PHRASES_PER_QUERY
    assert all(len(p.split()) <= MAX_PHRASE_TOKENS for p in phrases)
    assert all(len(p.split()) >= 2 for p in phrases)


def test_phrase_no_unbounded_ngrams_and_primary_intact():
    plan = formulate_lexical_query_plan(
        "alpha beta gamma delta epsilon zeta eta theta", language="en"
    )
    assert plan.phrase_count <= MAX_PHRASES_PER_QUERY
    assert plan.primary_token_count <= 8
    # Unigrams are not phrases
    assert all(len(p.split()) >= 2 for p in plan.phrases)


# --- B. Temporal ---


def test_temporal_today_yesterday_last_week_en():
    ref = datetime(2026, 9, 7, 15, 0, tzinfo=ZoneInfo("UTC"))
    today = parse_temporal_query_intent(
        "how am I today", language="en", reference_time=ref, timezone_name="UTC"
    )
    assert today.kind == "today"
    assert today.start == date(2026, 9, 7)
    assert today.deterministic_state == STATE_RESOLVED

    y = parse_temporal_query_intent(
        "summary yesterday", language="en", reference_time=ref, timezone_name="UTC"
    )
    assert y.kind == "yesterday"
    assert y.start == date(2026, 9, 6)

    w = parse_temporal_query_intent(
        "trends last week", language="en", reference_time=ref, timezone_name="UTC"
    )
    assert w.kind == "last_week"
    assert w.start == date(2026, 8, 31)
    assert w.end == date(2026, 9, 6)


def test_temporal_since_before_after_explicit_dates():
    since = parse_temporal_query_intent("changes since 2026-01-15", language="en")
    assert since.kind == "since"
    assert since.start == date(2026, 1, 15)
    assert since.deterministic_state == STATE_RESOLVED

    before = parse_temporal_query_intent("events before 2025-12-01", language="en")
    assert before.kind == "before"
    assert before.end == date(2025, 12, 1)

    after = parse_temporal_query_intent("events after 2025/06/01", language="en")
    assert after.kind == "after"
    assert after.start == date(2025, 6, 1)


def test_temporal_fa_ar_relative_forms():
    ref = datetime(2026, 9, 7, 12, 0, tzinfo=ZoneInfo("Asia/Tehran"))
    fa = parse_temporal_query_intent(
        "وضعیت امروز", language="fa", reference_time=ref, timezone_name="Asia/Tehran"
    )
    assert fa.kind == "today"
    assert fa.deterministic_state == STATE_RESOLVED

    ar = parse_temporal_query_intent(
        "الحالة امس", language="ar", reference_time=ref, timezone_name="Asia/Riyadh"
    )
    assert ar.kind == "yesterday"


def test_temporal_missing_context_ambiguous():
    amb = parse_temporal_query_intent("what about yesterday", language="en")
    assert amb.deterministic_state == STATE_AMBIGUOUS
    assert amb.clarification_required is True
    assert amb.start is None
    assert amb.end is None


def test_temporal_invalid_timezone_ambiguous():
    ref = datetime(2026, 9, 7, 12, 0)
    amb = parse_temporal_query_intent(
        "today summary",
        language="en",
        reference_time=ref,
        timezone_name="Not/AZone",
    )
    assert amb.deterministic_state == STATE_AMBIGUOUS
    assert amb.clarification_required is True


def test_temporal_personal_history_not_governed():
    ref = datetime(2026, 9, 7, 12, 0, tzinfo=ZoneInfo("UTC"))
    intent = parse_temporal_query_intent(
        "What was my blood pressure yesterday?",
        language="en",
        reference_time=ref,
        timezone_name="UTC",
    )
    assert intent.personal_history_intent is True
    assert intent.kind == "yesterday"

    db = MagicMock()
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=([_item(ku_id=1, canon="c1", statement="bp education")], {}),
    ):
        result = retrieve_knowledge_context(
            db,
            "What was my blood pressure yesterday?",
            language="en",
            reference_time=ref,
            timezone_name="UTC",
        )
    assert result.status == STATUS_INSUFFICIENT_CONTEXT
    assert result.items == []
    assert result.clarification_required is True
    assert "PERSONAL" in result.safe_user_facing_intent
    assert result.no_base_model_fallback is True
    assert result.sufficiency_audit["reason"] == SUFFICIENCY_PERSONAL_HISTORY_BLOCKED


# --- C. Alias ---


def test_alias_product_registry_empty_versioned():
    reg = get_product_alias_registry()
    assert "v1" in reg.version
    out = expand_query_aliases("blood pressure", language="en")
    assert out.expansions == ()
    assert out.authority == ALIAS_AUTHORITY


def test_alias_synthetic_max_four_dedupe_no_llm():
    reg = AliasRegistry(
        version="test-synth-v1",
        entries={
            "blood pressure": ("bp", "arterial pressure", "bp", "sys dia", "extra5"),
        },
    )
    out = expand_query_aliases(
        "blood pressure tips", language="en", registry=reg
    )
    assert len(out.expansions) <= MAX_ALIAS_EXPANSIONS_PER_QUERY
    assert len(out.expansions) == len(set(out.expansions))
    assert "bp" in out.expansions
    assert out.authority == ALIAS_AUTHORITY


def test_alias_unsupported_safe():
    reg = AliasRegistry(version="test-synth-v1", entries={"zzz": ("aaa",)})
    out = expand_query_aliases("unrelated query", language="en", registry=reg)
    assert out.expansions == ()


# --- D. Contradiction ---


def test_contradiction_none_when_compatible():
    items = [
        _item(ku_id=1, canon="a", statement="sleep hygiene helps", strength="HIGH"),
        _item(ku_id=2, canon="b", statement="sleep hygiene helps", strength="MODERATE"),
    ]
    assert detect_retrieval_set_contradictions(items) == ()
    d = evaluate_retrieval_sufficiency(items)
    assert d.sufficient is True
    assert d.reason == SUFFICIENCY_OK


def test_unrelated_topics_must_not_conflict():
    items = [
        _item(
            ku_id=1,
            canon="a",
            statement="prefer rest after exercise",
            strength="HIGH",
            domain="exercise",
            topic="recovery",
        ),
        _item(
            ku_id=2,
            canon="b",
            statement="prefer low-salt meals",
            strength="HIGH",
            domain="nutrition",
            topic="sodium",
        ),
    ]
    assert detect_retrieval_set_contradictions(items) == ()
    assert evaluate_retrieval_sufficiency(items).sufficient is True


def test_evidence_strength_only_must_not_create_contradiction():
    items = [
        _item(ku_id=1, canon="a", statement="hydrate regularly", strength="HIGH"),
        _item(ku_id=2, canon="b", statement="hydrate regularly", strength="LOW"),
    ]
    assert detect_retrieval_set_contradictions(items) == ()


def test_contradiction_unresolved_fail_closed():
    items = [
        _item(ku_id=1, canon="a", statement="do X for sleep", strength="HIGH"),
        _item(ku_id=2, canon="b", statement="avoid X for sleep", strength="HIGH"),
    ]
    hits = detect_retrieval_set_contradictions(items)
    assert hits
    assert hits[0].conflict_state in {"SUSPECTED", "CONFIRMED"}
    d = evaluate_retrieval_sufficiency(items)
    assert d.sufficient is False
    assert d.reason == SUFFICIENCY_UNRESOLVED_CONFLICT
    assert d.clarification_required is True


def test_contradiction_serving_path_clears_items():
    items = [
        _item(ku_id=1, canon="a", statement="prefer rest", strength="HIGH"),
        _item(ku_id=2, canon="b", statement="prefer activity", strength="HIGH"),
    ]
    db = MagicMock()
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, {"effective_mode": "hybrid"}),
    ):
        result = retrieve_knowledge_context(db, "sleep guidance", language="en")
    assert result.status == STATUS_INSUFFICIENT_CONTEXT
    assert result.items == []
    assert result.clarification_required is True
    assert result.no_base_model_fallback is True


def test_lower_authority_cannot_override_via_conflict_clearance():
    # Both governed; unresolved conflict clears the whole set (no override).
    governed = _item(ku_id=1, canon="gov", statement="guidance A", strength="HIGH")
    other = _item(ku_id=2, canon="low", statement="guidance B", strength="LOW")
    d = evaluate_retrieval_sufficiency([governed, other])
    assert d.sufficient is False
    assert d.reason == SUFFICIENCY_UNRESOLVED_CONFLICT


# --- E. Sufficiency ---


def test_sufficiency_zero_eligible():
    d = evaluate_retrieval_sufficiency([])
    assert d.sufficient is False
    assert d.reason == SUFFICIENCY_NO_ELIGIBLE


def test_sufficiency_low_only_fail_closed():
    items = [
        _item(ku_id=1, canon="a", statement="weak tip one", strength="LOW"),
        _item(ku_id=2, canon="b", statement="weak tip two", strength="LOW", topic="other"),
    ]
    d = evaluate_retrieval_sufficiency(items)
    assert d.sufficient is False
    assert d.reason == SUFFICIENCY_LOW_ONLY


def test_sufficiency_moderate_and_high_ok():
    mod = [_item(ku_id=1, canon="a", statement="mod tip", strength="MODERATE")]
    high = [_item(ku_id=2, canon="b", statement="high tip", strength="HIGH")]
    assert evaluate_retrieval_sufficiency(mod).sufficient is True
    assert evaluate_retrieval_sufficiency(high).sufficient is True


def test_sufficiency_serving_moderate_ok_and_no_base_model_fallback():
    items = [_item(ku_id=1, canon="a", statement="sleep hygiene basics", strength="MODERATE")]
    db = MagicMock()
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, {"effective_mode": "hybrid"}),
    ):
        result = retrieve_knowledge_context(db, "sleep hygiene", language="en")
    assert result.status == STATUS_OK
    assert len(result.items) == 1
    assert result.items[0].as_care_snippet()["authority_label"] == AUTHORITY_LABEL_GOVERNED
    assert_no_base_model_medical_fallback(result)


def test_temporal_ambiguous_serving_fail_closed():
    db = MagicMock()
    result = retrieve_knowledge_context(db, "how was yesterday", language="en")
    assert result.status == STATUS_INSUFFICIENT_CONTEXT
    assert result.clarification_required is True
    assert result.items == []


# --- F. Phase1 adjacent regression locks ---


def test_phase1_openai_contract_unchanged():
    from backend.app.services.scis import (
        DEFAULT_EMBEDDING_DIM,
        DEFAULT_EMBEDDING_MODEL,
        DEFAULT_EMBEDDING_PROVIDER,
    )
    from backend.app.services.scis.embedding.providers import (
        CohereEmbeddingProvider,
        get_default_provider,
        resolve_product_governed_embedding,
    )
    from backend.app.services.local_rag import provider_router

    assert DEFAULT_EMBEDDING_PROVIDER == "openai"
    assert DEFAULT_EMBEDDING_MODEL == "text-embedding-3-large"
    assert DEFAULT_EMBEDDING_DIM == 1024
    assert provider_router.STAGE17_VECTOR_PRODUCT_CHAT_DISABLED is True
    assert provider_router.stage17_vector_reachable_from_product_chat() is False

    offline = get_default_provider(allow_network=False)
    assert offline.provider_name == "fake"

    import os

    os.environ["OPENAI_API_KEY"] = "sk-test-realish-key"
    os.environ["COHERE_API_KEY"] = "should-not-win"
    net = get_default_provider(allow_network=True)
    assert net.provider_name == "openai"
    assert not isinstance(net, CohereEmbeddingProvider)

    os.environ.pop("OPENAI_API_KEY", None)
    prov, mode = resolve_product_governed_embedding(allow_network=True)
    assert prov is None
    assert mode == "lexical"


def test_unsupported_language_still_fail_closed():
    db = MagicMock()
    result = retrieve_knowledge_context(db, "bonjour", language="fr")
    assert result.status == "UNSUPPORTED_LANGUAGE"
    assert result.clarification_required is True
