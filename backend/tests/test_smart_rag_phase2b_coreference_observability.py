"""Phase2-B Smart-RAG — authority-safe coreference + observability focused proofs."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.app.services.i5.runtime_knowledge_retrieval import (
    AUTHORITY_LABEL_GOVERNED,
    STATUS_INSUFFICIENT_CONTEXT,
    STATUS_OK,
    RetrievedKnowledgeItem,
    retrieve_knowledge_context,
)
from backend.app.services.scis.coreference import (
    AUTHORITY_GOVERNED,
    AUTHORITY_PERSONAL,
    SCOPE_MANAGED,
    SCOPE_SELF,
    STATE_AMBIGUOUS,
    STATE_NOT_APPLICABLE,
    STATE_RESOLVED,
    STATE_UNRESOLVED,
    TYPE_HEALTH_SUBJECT,
    TYPE_MEDICATION,
    TYPE_RESULT,
    TYPE_TOPIC,
    StructuredReferent,
    resolve_coreference,
)
from backend.app.services.scis.contracts import FallbackState, RetrievalMode


def _item(**kwargs) -> RetrievedKnowledgeItem:
    defaults = dict(
        knowledge_unit_id=1,
        canonical_unit_id="c1",
        immutable_version_id="v1",
        memory_item_id="SCIS_KCE:1",
        memory_row_id=0,
        source_profile_id=1,
        provenance_id=1,
        raw_evidence_id=1,
        domain="lifestyle",
        language="en",
        topic_taxonomy="sleep",
        normalized_statement="sleep hygiene basics",
        evidence_strength="MODERATE",
        freshness_state="CURRENT",
        conflict_state="NONE",
        medical_safety_state="CLEARED",
        runtime_eligibility="ELIGIBLE",
        rank_score=100,
        inclusion_reasons=["GOVERNED", "SCIS_HYBRID"],
    )
    defaults.update(kwargs)
    return RetrievedKnowledgeItem(**defaults)


def _ref(**kwargs) -> StructuredReferent:
    base = dict(
        referent_type=TYPE_TOPIC,
        referent_key="topic-1",
        authority_label=AUTHORITY_PERSONAL,
        source_scope=SCOPE_SELF,
        authorized=True,
        retrieval_hint="sleep",
    )
    base.update(kwargs)
    return StructuredReferent(**base)


# --- CASE09 coreference unit ---


def test_coref_not_applicable_plain_query():
    r = resolve_coreference("healthy sleep tips", language="en", referents=[_ref()])
    assert r.state == STATE_NOT_APPLICABLE
    assert r.clarification_required is False


def test_coref_health_subject_unambiguous_mother():
    mother = _ref(
        referent_type=TYPE_HEALTH_SUBJECT,
        referent_key="hs-mother-1",
        source_scope=SCOPE_MANAGED,
        authority_label=AUTHORITY_PERSONAL,
        retrieval_hint="als-care",
    )
    r = resolve_coreference("How was she yesterday?", language="en", referents=[mother])
    assert r.state == STATE_RESOLVED
    assert r.referent_key == "hs-mother-1"
    assert r.source_scope == SCOPE_MANAGED


def test_coref_self_and_mother_ambiguous():
    refs = [
        _ref(referent_type=TYPE_HEALTH_SUBJECT, referent_key="self", source_scope=SCOPE_SELF),
        _ref(
            referent_type=TYPE_HEALTH_SUBJECT,
            referent_key="mother",
            source_scope=SCOPE_MANAGED,
        ),
    ]
    r = resolve_coreference("How was she yesterday?", language="en", referents=refs)
    assert r.state == STATE_AMBIGUOUS
    assert r.clarification_required is True


def test_coref_no_health_subject_unresolved():
    r = resolve_coreference("How was she yesterday?", language="en", referents=[])
    assert r.state == STATE_UNRESOLVED
    assert r.clarification_required is True


def test_coref_medication_one_two_none():
    one = [_ref(referent_type=TYPE_MEDICATION, referent_key="med-a", retrieval_hint="med-a")]
    assert resolve_coreference("what about that medicine?", language="en", referents=one).state == STATE_RESOLVED
    two = one + [
        _ref(referent_type=TYPE_MEDICATION, referent_key="med-b", retrieval_hint="med-b")
    ]
    assert resolve_coreference("what about that medicine?", language="en", referents=two).state == STATE_AMBIGUOUS
    assert resolve_coreference("what about that medicine?", language="en", referents=[]).state == STATE_UNRESOLVED


def test_coref_result_one_and_missing():
    one = [_ref(referent_type=TYPE_RESULT, referent_key="res-1", retrieval_hint="lab-panel")]
    assert resolve_coreference("what about the last result?", language="en", referents=one).state == STATE_RESOLVED
    assert resolve_coreference("what about the last result?", language="en", referents=[]).state == STATE_UNRESOLVED


def test_coref_unauthorized_ignored():
    bad = _ref(referent_type=TYPE_MEDICATION, referent_key="x", authorized=False)
    r = resolve_coreference("that medicine", language="en", referents=[bad])
    assert r.state == STATE_UNRESOLVED


def test_coref_fa_ar_cues():
    med = [_ref(referent_type=TYPE_MEDICATION, referent_key="m1")]
    assert resolve_coreference("همان دارو چطور؟", language="fa", referents=med).state == STATE_RESOLVED
    assert resolve_coreference("ماذا عن ذلك الدواء", language="ar", referents=med).state == STATE_RESOLVED
    mother = [
        _ref(
            referent_type=TYPE_HEALTH_SUBJECT,
            referent_key="m",
            source_scope=SCOPE_MANAGED,
        )
    ]
    assert resolve_coreference("مادرم چطور بود؟", language="fa", referents=mother).state == STATE_RESOLVED


def test_coref_serving_ambiguous_fail_closed_preserves_query():
    refs = [
        _ref(referent_type=TYPE_MEDICATION, referent_key="a"),
        _ref(referent_type=TYPE_MEDICATION, referent_key="b"),
    ]
    q = "what about that medicine?"
    result = retrieve_knowledge_context(
        MagicMock(), q, language="en", referent_context=refs
    )
    assert result.status == STATUS_INSUFFICIENT_CONTEXT
    assert result.original_query == q
    assert result.items == []
    assert result.clarification_required is True
    assert result.observability["coreference_state"] == STATE_AMBIGUOUS


def test_coref_personal_resolved_does_not_elevate_authority_label_on_items():
    refs = [
        _ref(
            referent_type=TYPE_MEDICATION,
            referent_key="med-personal",
            authority_label=AUTHORITY_PERSONAL,
            retrieval_hint="hydration",
        )
    ]
    items = [_item()]
    meta = {
        "effective_mode": "hybrid",
        "retrieval_mode": "hybrid",
        "language": "en",
        "provider": "openai",
        "fallback_state": "none",
        "lexical_count": 2,
        "semantic_count": 2,
        "rrf_count": 3,
        "authority_label": "GOVERNED",
        "cohere_used": False,
        "stage17_rag_embeddings_used": False,
    }
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, meta),
    ) as mocked:
        result = retrieve_knowledge_context(
            MagicMock(),
            "what about that medicine?",
            language="en",
            referent_context=refs,
        )
    assert result.original_query == "what about that medicine?"
    assert result.status == STATUS_OK
    assert result.items[0].as_care_snippet()["authority_label"] == AUTHORITY_LABEL_GOVERNED
    assert result.query_intelligence["coreference"]["coreference_authority_label"] == AUTHORITY_PERSONAL
    # Original query passed to SCIS (not replaced).
    assert mocked.call_args.args[1] == "what about that medicine?"


def test_coref_no_account_or_subject_substitution():
    # Mother cue must not resolve to SELF when only SELF present.
    self_only = [
        _ref(referent_type=TYPE_HEALTH_SUBJECT, referent_key="self", source_scope=SCOPE_SELF)
    ]
    r = resolve_coreference("How was my mother?", language="en", referents=self_only)
    assert r.state == STATE_UNRESOLVED
    assert r.clarification_required is True


def test_family_scenario_son_self_vs_mother_managed():
    """SEDI-V1-REAL-FAMILY-CARE-E2E-01 synthetic mirror (no PII, no Mother Account)."""
    son_self = _ref(
        referent_type=TYPE_HEALTH_SUBJECT,
        referent_key="hs-son-self-1",
        source_scope=SCOPE_SELF,
        authority_label=AUTHORITY_PERSONAL,
        retrieval_hint="self-care",
    )
    mother_managed = _ref(
        referent_type=TYPE_HEALTH_SUBJECT,
        referent_key="hs-mother-managed-1",
        source_scope=SCOPE_MANAGED,
        authority_label=AUTHORITY_PERSONAL,
        retrieval_hint="care-topic",  # opaque non-clinical label; no disease text in observability
    )
    assert son_self.referent_key != mother_managed.referent_key

    # A) mother cue + Mother MANAGED only
    a = resolve_coreference("How was my mother?", language="en", referents=[mother_managed])
    assert a.state == STATE_RESOLVED
    assert a.referent_key == "hs-mother-managed-1"
    assert a.source_scope == SCOPE_MANAGED

    # B) mother cue + SELF only
    b = resolve_coreference("How was my mother?", language="en", referents=[son_self])
    assert b.state == STATE_UNRESOLVED

    # C) she + both subjects
    c = resolve_coreference("How was she yesterday?", language="en", referents=[son_self, mother_managed])
    assert c.state == STATE_AMBIGUOUS

    # D) explicit self cue with both present → SELF only
    d = resolve_coreference("what about myself?", language="en", referents=[son_self, mother_managed])
    assert d.state == STATE_RESOLVED
    assert d.referent_key == "hs-son-self-1"
    assert d.source_scope == SCOPE_SELF

    # E) generic cue with multiple typed referents → AMBIGUOUS
    e = resolve_coreference(
        "what about it?",
        language="en",
        referents=[son_self, _ref(referent_type=TYPE_MEDICATION, referent_key="med-1")],
    )
    assert e.state == STATE_AMBIGUOUS

    # F) audit must not contain clinical disease strings (avoid substring false positives).
    audit = a.to_audit_dict()
    blob = str(audit).lower()
    assert "amyotrophic" not in blob
    assert "als " not in blob and " als" not in blob and blob.strip() != "als"
    assert "disease" not in blob


# --- CASE28 observability ---


def test_observability_propagates_from_scis_meta():
    items = [_item()]
    meta = {
        "effective_mode": "lexical",
        "retrieval_mode": "lexical",
        "language": "en",
        "provider": "none_lexical",
        "fallback_state": "none",
        "provider_failure": None,
        "lexical_count": 4,
        "semantic_count": 0,
        "rrf_count": 4,
        "latency_ms": 12.5,
        "timings_ms": {"lexical_ms": 12.5},
        "governance_drop_counts": {"retracted": 1},
        "openai_failure_lexical_fallback": False,
        "cohere_used": False,
        "stage17_rag_embeddings_used": False,
        "authority_label": "GOVERNED",
    }
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, meta),
    ):
        result = retrieve_knowledge_context(MagicMock(), "sleep hygiene", language="en")
    obs = result.observability
    assert obs["retrieval_mode"] == "lexical"
    assert obs["language"] == "en"
    assert obs["provider"] == "none_lexical"
    assert obs["fallback_state"] == "none"
    assert obs["lexical_count"] == 4
    assert obs["semantic_count"] == 0
    assert obs["rrf_count"] == 4
    assert obs["final_evidence_count"] == 1
    assert obs["latency_ms"] == 12.5
    assert obs["governance_drop_counts"]["retracted"] == 1
    assert obs["coreference_state"] == STATE_NOT_APPLICABLE
    assert "clarification_required" in obs
    envelope = result.to_dict()
    assert "original_query" not in obs
    assert "embedding" not in obs
    assert "api_key" not in str(obs).lower()
    assert envelope["final_evidence_count"] == 1


def test_observability_hybrid_fallback_and_provider_failure():
    items = [_item()]
    meta = {
        "effective_mode": "lexical",
        "retrieval_mode": "lexical",
        "language": "en",
        "provider": "openai",
        "fallback_state": "embedding_failure",
        "provider_failure": "TimeoutError",
        "lexical_count": 3,
        "semantic_count": 0,
        "rrf_count": 3,
        "openai_failure_lexical_fallback": True,
        "cohere_used": False,
        "stage17_rag_embeddings_used": False,
    }
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, meta),
    ):
        result = retrieve_knowledge_context(MagicMock(), "sleep tips", language="en")
    assert result.observability["openai_failure_lexical_fallback"] is True
    assert result.observability["provider_failure"] == "TimeoutError"
    assert result.observability["cohere_used"] is False
    assert result.observability["stage17_rag_embeddings_used"] is False


def test_observability_does_not_alter_items_when_meta_changes():
    items = [_item(canonical_unit_id="stable")]
    meta = {
        "effective_mode": "hybrid",
        "retrieval_mode": "hybrid",
        "language": "en",
        "provider": "openai",
        "fallback_state": "none",
        "lexical_count": 1,
        "semantic_count": 1,
        "rrf_count": 1,
    }
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, meta),
    ):
        a = retrieve_knowledge_context(MagicMock(), "sleep hygiene", language="en")
    meta2 = dict(meta)
    meta2["lexical_count"] = 99
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, meta2),
    ):
        b = retrieve_knowledge_context(MagicMock(), "sleep hygiene", language="en")
    assert a.items[0].canonical_unit_id == b.items[0].canonical_unit_id
    assert a.items[0].rank_score == b.items[0].rank_score


def test_adapter_builds_count_fields_from_scis_response():
    from backend.app.services.scis.governed_runtime_adapter import retrieve_scis_governed_runtime_items

    fake_resp = SimpleNamespace(
        evidence=[],
        fallback_state=FallbackState.NO_RESULTS,
        candidate_counts={"lexical_count": 5, "semantic_count": 2, "rrf_count": 6, "lexical_eligible": 5, "vector_eligible": 2},
        filtered_counts={"retracted": 2},
        timings_ms={"lexical_ms": 1.0, "vector_ms": 2.0, "fusion_ms": 0.5},
        error_class=None,
    )
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.resolve_product_governed_embedding",
        return_value=(None, RetrievalMode.LEXICAL.value),
    ):
        with patch(
            "backend.app.services.scis.governed_runtime_adapter.retrieve",
            return_value=fake_resp,
        ):
            items, meta = retrieve_scis_governed_runtime_items(
                MagicMock(), "q", language="en", allow_network=False, force_mode=RetrievalMode.LEXICAL
            )
    assert items == []
    assert meta["lexical_count"] == 5
    assert meta["semantic_count"] == 2
    assert meta["rrf_count"] == 6
    assert meta["governance_drop_counts"]["retracted"] == 2
    assert meta["latency_ms"] == 3.5
    assert meta["provider"] == "none_lexical"
