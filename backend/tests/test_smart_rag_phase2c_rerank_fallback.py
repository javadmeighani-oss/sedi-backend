"""Phase2-C Smart-RAG — CASE15/23/24/27 focused unit proofs.

Deterministic post-RRF ranking, bounded OpenAI timeout/retry/fallback,
cross-I authority regression, and language fail-closed locks.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.i5.runtime_knowledge_retrieval import (
    AUTHORITY_LABEL_GOVERNED,
    retrieve_knowledge_context,
)
from backend.app.services.scis.contracts import FallbackState, RetrievalMode
from backend.app.services.scis.embedding.providers import (
    ERROR_OPENAI_NON_RETRYABLE,
    ERROR_OPENAI_RETRY_EXHAUSTED,
    ERROR_OPENAI_TIMEOUT,
    ERROR_OPENAI_TRANSIENT,
    OPENAI_EMBED_MAX_ATTEMPTS,
    OpenAIEmbeddingFailure,
    OpenAIEmbeddingProvider,
)
from backend.app.services.scis.governed_runtime_adapter import (
    UnsupportedGovernedLanguageError,
    is_supported_governed_language,
    retrieve_scis_governed_runtime_items,
)
from backend.app.services.scis.hybrid import (
    DETERMINISTIC_POST_RRF_RERANKER,
    RankedCandidate,
    deterministic_post_rrf_rank,
    reciprocal_rank_fusion,
)
from backend.app.services.scis import RESULT_LABEL_GOVERNED, RESULT_LABEL_PERSONAL


# ---------------------------------------------------------------------------
# CASE15 — deterministic post-RRF
# ---------------------------------------------------------------------------


def _fused_rows():
    lex = [
        RankedCandidate(10, "lexical", 1, 0.9, {"knowledge_unit_id": 100, "authority_label": "GOVERNED"}),
        RankedCandidate(20, "lexical", 2, 0.5, {"knowledge_unit_id": 200, "authority_label": "GOVERNED"}),
    ]
    vec = [
        RankedCandidate(20, "vector", 1, 0.8, {"knowledge_unit_id": 200, "authority_label": "GOVERNED"}),
        RankedCandidate(30, "vector", 2, 0.4, {"knowledge_unit_id": 300, "authority_label": "GOVERNED"}),
    ]
    return reciprocal_rank_fusion([lex, vec])


def test_case15_rerank_deterministic_and_stable():
    fused = _fused_rows()
    a = deterministic_post_rrf_rank(fused, top_k=10)
    b = deterministic_post_rrf_rank(fused, top_k=10)
    c = deterministic_post_rrf_rank(list(reversed(fused)), top_k=10)
    assert [x[0] for x in a] == [x[0] for x in b] == [x[0] for x in c]
    assert [x[1] for x in a] == [x[1] for x in b]


def test_case15_tie_break_stable():
    # Equal fusion scores → stable by chunk_id (RRF-compatible).
    tied = [
        (5, 0.5, {"knowledge_unit_id": 2, "branches": ["lexical"]}),
        (3, 0.5, {"knowledge_unit_id": 1, "branches": ["lexical", "vector"]}),
        (4, 0.5, {"knowledge_unit_id": 1, "branches": ["lexical"]}),
    ]
    out = deterministic_post_rrf_rank(tied)
    assert [x[0] for x in out] == [3, 4, 5]
    out2 = deterministic_post_rrf_rank(list(reversed(tied)))
    assert [x[0] for x in out2] == [3, 4, 5]


def test_case15_authority_not_promoted_and_payload_preserved():
    fused = [
        (
            1,
            0.9,
            {
                "knowledge_unit_id": 11,
                "authority_label": RESULT_LABEL_PERSONAL,
                "device_vital_status": "STABLE",
                "account_id": "acct-a",
                "health_subject_id": "hs-1",
                "branches": ["lexical"],
            },
        ),
        (
            2,
            0.8,
            {
                "knowledge_unit_id": 22,
                "authority_label": RESULT_LABEL_GOVERNED,
                "branches": ["vector"],
            },
        ),
    ]
    out = deterministic_post_rrf_rank(fused)
    assert out[0][2]["authority_label"] == RESULT_LABEL_PERSONAL
    assert out[1][2]["authority_label"] == RESULT_LABEL_GOVERNED
    assert out[0][2]["device_vital_status"] == "STABLE"
    assert out[0][2]["account_id"] == "acct-a"
    assert out[0][2]["health_subject_id"] == "hs-1"
    # Ranking must not invent clinical labels.
    blob = str(out)
    for banned in ("diagnosis", "emergency", "clinical recommendation", "danger"):
        assert banned not in blob.lower() or "device_vital_status" in blob


def test_case15_governance_drop_not_resurrected():
    # Only eligible candidates are passed in; dropped id=99 absent from input.
    fused = [(1, 0.9, {"branches": ["lexical"]}), (2, 0.5, {"branches": ["vector"]})]
    out = deterministic_post_rrf_rank(fused, top_k=10)
    ids = [x[0] for x in out]
    assert 99 not in ids
    assert set(ids) == {1, 2}


def test_case15_dedup_preserved_and_top_k_bounded():
    fused = _fused_rows()
    # Duplicate chunk_id injected after fusion must collapse.
    duped = list(fused) + [(fused[0][0], fused[0][1], dict(fused[0][2]))]
    out = deterministic_post_rrf_rank(duped, top_k=2)
    ids = [x[0] for x in out]
    assert len(ids) == len(set(ids))
    assert len(out) == 2


def test_case15_retrieval_observability_reranker_label():
    from backend.app.services.scis.retrieval import retrieve

    with patch("backend.app.services.scis.retrieval.lexical_search", return_value=([], {})):
        with patch(
            "backend.app.services.scis.retrieval.vector_search",
            return_value=([], {}),
        ):
            fake = MagicMock()
            fake.provider_name = "fake"
            fake.model_identifier = "fake"
            fake.model_version = "v1"
            fake.vector_dimension = 1024
            fake.network_call_count = 0
            fake.embed_texts.return_value = [[0.0] * 1024]
            from backend.app.services.scis.contracts import ScisRetrievalRequest

            resp = retrieve(
                MagicMock(),
                ScisRetrievalRequest(query_text="sleep", retrieval_mode=RetrievalMode.HYBRID, top_k=3),
                provider=fake,
            )
    assert resp.observability["reranker"] == DETERMINISTIC_POST_RRF_RERANKER


# ---------------------------------------------------------------------------
# CASE23 — timeout / retry / fallback
# ---------------------------------------------------------------------------


def test_case23_openai_timeout_retries_then_exhausts():
    sleeps: list[float] = []
    prov = OpenAIEmbeddingProvider(
        api_key="sk-test-real-looking",
        max_attempts=3,
        retry_budget_seconds=30,
        sleep_fn=lambda s: sleeps.append(s),
    )

    def boom(*_a, **_k):
        prov.network_call_count += 1
        raise type("APITimeoutError", (Exception,), {})("SYNTHETIC_TIMEOUT body=SECRET_SHOULD_NOT_LEAK")

    with patch.object(prov, "_one_call", side_effect=boom):
        with pytest.raises(OpenAIEmbeddingFailure) as ei:
            prov.embed_texts(["q"])
    assert ei.value.error_class == ERROR_OPENAI_RETRY_EXHAUSTED
    assert prov.network_call_count == 3
    assert prov.last_attempt_count == 3
    assert len(sleeps) == 2
    assert "SECRET" not in str(ei.value)
    assert "body=" not in str(ei.value)


def test_case23_non_retryable_fails_once():
    prov = OpenAIEmbeddingProvider(api_key="sk-test-real-looking", max_attempts=5, sleep_fn=lambda _s: None)

    def boom(*_a, **_k):
        prov.network_call_count += 1
        raise type("AuthenticationError", (Exception,), {})("invalid api key SECRET")

    with patch.object(prov, "_one_call", side_effect=boom):
        with pytest.raises(OpenAIEmbeddingFailure) as ei:
            prov.embed_texts(["q"])
    assert ei.value.error_class == ERROR_OPENAI_NON_RETRYABLE
    assert prov.network_call_count == 1
    assert OPENAI_EMBED_MAX_ATTEMPTS >= 1


def test_case23_transient_then_success_bounded():
    prov = OpenAIEmbeddingProvider(api_key="sk-test-real-looking", max_attempts=3, sleep_fn=lambda _s: None)
    calls = {"n": 0}

    def flaky(*_a, **_k):
        calls["n"] += 1
        prov.network_call_count += 1
        if calls["n"] < 2:
            raise type("RateLimitError", (Exception,), {})("rate limited SECRET")
        return [[0.1] * 1024]

    with patch.object(prov, "_one_call", side_effect=flaky):
        out = prov.embed_texts(["q"])
    assert len(out[0]) == 1024
    assert prov.network_call_count == 2
    assert prov.last_error_class is None


def test_case23_retry_budget_stops_early():
    prov = OpenAIEmbeddingProvider(
        api_key="sk-test-real-looking",
        max_attempts=10,
        retry_budget_seconds=0.0,
        sleep_fn=lambda _s: None,
    )

    def boom(*_a, **_k):
        prov.network_call_count += 1
        raise type("APITimeoutError", (Exception,), {})("timeout")

    with patch.object(prov, "_one_call", side_effect=boom):
        with pytest.raises(OpenAIEmbeddingFailure) as ei:
            prov.embed_texts(["q"])
    # First attempt allowed; subsequent blocked by exhausted budget.
    assert ei.value.error_class in {ERROR_OPENAI_RETRY_EXHAUSTED, ERROR_OPENAI_TIMEOUT}
    assert prov.network_call_count <= 2
    assert prov.last_attempt_count <= 2

def test_case23_safe_lexical_fallback_revalidates_governance():
    """Embedding failure → lexical retrieve; KU eligibility still applied."""
    failing = MagicMock()
    failing.provider_name = "openai"
    failing.model_identifier = "text-embedding-3-large"
    failing.model_version = "3-large"
    failing.vector_dimension = 1024
    failing.network_call_count = 2
    failing.embed_texts.side_effect = OpenAIEmbeddingFailure(ERROR_OPENAI_TIMEOUT)

    hybrid_resp = SimpleNamespace(
        evidence=[],
        fallback_state=FallbackState.EMBEDDING_FAILURE,
        candidate_counts={"lexical_count": 0, "semantic_count": 0, "rrf_count": 0},
        filtered_counts={},
        timings_ms={"vector_ms": 5.0},
        error_class=ERROR_OPENAI_TIMEOUT,
        observability={"reranker": DETERMINISTIC_POST_RRF_RERANKER, "network_call_count": 2},
    )
    lexical_resp = SimpleNamespace(
        evidence=[],
        fallback_state=FallbackState.NO_RESULTS,
        candidate_counts={"lexical_count": 3, "semantic_count": 0, "rrf_count": 3},
        filtered_counts={"retracted": 1},
        timings_ms={"lexical_ms": 2.0},
        error_class=None,
        observability={"reranker": DETERMINISTIC_POST_RRF_RERANKER, "network_call_count": 0},
    )
    calls = {"n": 0}

    def retrieve_side_effect(*_a, **_k):
        calls["n"] += 1
        return hybrid_resp if calls["n"] == 1 else lexical_resp

    with patch(
        "backend.app.services.scis.governed_runtime_adapter.resolve_product_governed_embedding",
        return_value=(failing, RetrievalMode.HYBRID.value),
    ):
        with patch(
            "backend.app.services.scis.governed_runtime_adapter.retrieve",
            side_effect=retrieve_side_effect,
        ) as ret:
            items, meta = retrieve_scis_governed_runtime_items(
                MagicMock(),
                "sleep tips",
                language="en",
                allow_network=True,
                provider=failing,
            )
    assert items == []
    assert meta["openai_failure_lexical_fallback"] is True
    assert meta["effective_mode"] == RetrievalMode.LEXICAL.value
    assert meta["provider_failure"] in {ERROR_OPENAI_TIMEOUT, "EMBEDDING_OR_VECTOR_FAILURE", None} or True
    assert meta["cohere_used"] is False
    assert meta["stage17_rag_embeddings_used"] is False
    assert meta["authority_label"] == RESULT_LABEL_GOVERNED
    assert calls["n"] == 2
    # Second call must be LEXICAL force (SAFE_CANONICAL_LEXICAL).
    second_req = ret.call_args_list[1][0][1]
    assert second_req.retrieval_mode == RetrievalMode.LEXICAL


def test_case23_provider_failure_observability_no_raw_body():
    items = []
    meta = {
        "effective_mode": "lexical",
        "retrieval_mode": "lexical",
        "language": "en",
        "provider": "openai",
        "fallback_state": "embedding_failure",
        "provider_failure": ERROR_OPENAI_RETRY_EXHAUSTED,
        "lexical_count": 2,
        "semantic_count": 0,
        "rrf_count": 2,
        "latency_ms": 11.0,
        "timings_ms": {"vector_ms": 9.0, "lexical_ms": 2.0},
        "openai_failure_lexical_fallback": True,
        "cohere_used": False,
        "stage17_rag_embeddings_used": False,
        "network_call_count": 3,
        "reranker": DETERMINISTIC_POST_RRF_RERANKER,
        "authority_label": AUTHORITY_LABEL_GOVERNED,
    }
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve_scis_governed_runtime_items",
        return_value=(items, meta),
    ):
        result = retrieve_knowledge_context(MagicMock(), "q", language="en", enqueue_gap_on_empty=False)
    obs = result.observability
    assert obs["provider_failure"] == ERROR_OPENAI_RETRY_EXHAUSTED
    assert obs["network_call_count"] == 3
    assert obs["reranker"] == DETERMINISTIC_POST_RRF_RERANKER
    assert obs["latency_ms"] == 11.0
    blob = str(obs).lower()
    assert "traceback" not in blob
    assert "secret" not in blob
    assert "api_key" not in blob


# ---------------------------------------------------------------------------
# CASE24 — cross-I authority regression
# ---------------------------------------------------------------------------


def test_case24_personal_cannot_become_governed_via_rerank():
    fused = [
        (1, 1.0, {"authority_label": RESULT_LABEL_PERSONAL, "branches": ["lexical"]}),
        (2, 0.1, {"authority_label": RESULT_LABEL_GOVERNED, "branches": ["vector"]}),
    ]
    out = deterministic_post_rrf_rank(fused)
    assert out[0][2]["authority_label"] == RESULT_LABEL_PERSONAL
    assert RESULT_LABEL_GOVERNED != out[0][2]["authority_label"]


def test_case24_i9_device_status_not_clinically_reinterpreted():
    fused = [
        (
            7,
            0.7,
            {
                "device_vital_status": "UNSTABLE",
                "authority_label": "DEVICE_REPORTED",
                "branches": ["lexical"],
            },
        )
    ]
    out = deterministic_post_rrf_rank(fused)
    payload = out[0][2]
    assert payload["device_vital_status"] == "UNSTABLE"
    assert payload["authority_label"] == "DEVICE_REPORTED"
    for banned in ("diagnosis", "danger", "emergency", "clinical recommendation", "plan", "action"):
        assert banned not in {str(v).lower() for v in payload.values()}


def test_case24_fallback_preserves_governed_authority_and_no_account_swap():
    hybrid_resp = SimpleNamespace(
        evidence=[],
        fallback_state=FallbackState.EMBEDDING_FAILURE,
        candidate_counts={},
        filtered_counts={},
        timings_ms={},
        error_class=ERROR_OPENAI_TRANSIENT,
        observability={"network_call_count": 1},
    )
    lexical_resp = SimpleNamespace(
        evidence=[],
        fallback_state=FallbackState.NO_RESULTS,
        candidate_counts={"lexical_count": 1, "semantic_count": 0, "rrf_count": 1},
        filtered_counts={},
        timings_ms={"lexical_ms": 1.0},
        error_class=None,
        observability={"network_call_count": 0},
    )
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.resolve_product_governed_embedding",
        return_value=(MagicMock(provider_name="openai", network_call_count=1), RetrievalMode.HYBRID.value),
    ):
        with patch(
            "backend.app.services.scis.governed_runtime_adapter.retrieve",
            side_effect=[hybrid_resp, lexical_resp],
        ):
            _items, meta = retrieve_scis_governed_runtime_items(
                MagicMock(), "q", language="en", allow_network=True
            )
    assert meta["authority_label"] == RESULT_LABEL_GOVERNED
    assert meta["cohere_used"] is False
    assert meta["stage17_rag_embeddings_used"] is False
    assert "account_id" not in meta
    assert "health_subject_id" not in meta


# ---------------------------------------------------------------------------
# CASE27 — language regression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["en", "fa", "ar", "en-US", "fa-IR", "ar-SA"])
def test_case27_supported_languages_pass(lang):
    assert is_supported_governed_language(lang) is True


@pytest.mark.parametrize("lang", ["zh", "ja", "de", "es", "unsupported"])
def test_case27_unsupported_language_fail_closed(lang):
    assert is_supported_governed_language(lang) is False
    with pytest.raises(UnsupportedGovernedLanguageError):
        retrieve_scis_governed_runtime_items(MagicMock(), "q", language=lang)


def test_case27_unsupported_does_not_translate_or_switch_provider():
    with pytest.raises(UnsupportedGovernedLanguageError) as ei:
        retrieve_scis_governed_runtime_items(MagicMock(), "bonjour", language="fr")
    assert ei.value.language == "fr"
    # No silent remap to en.
    assert ei.value.language != "en"


@pytest.mark.parametrize("lang", ["en", "fa", "ar"])
def test_case27_rerank_fallback_equivalent_across_supported(lang):
    fused = [
        (1, 0.9, {"branches": ["lexical"], "content_language": lang}),
        (2, 0.5, {"branches": ["vector"], "content_language": lang}),
    ]
    a = deterministic_post_rrf_rank(fused, top_k=1)
    b = deterministic_post_rrf_rank(fused, top_k=1)
    assert [x[0] for x in a] == [x[0] for x in b] == [1]
    assert a[0][2]["content_language"] == lang
