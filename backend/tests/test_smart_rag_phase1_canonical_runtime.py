"""Phase1 Smart-RAG canonical runtime foundation — focused unit proofs.

Pure unit tests use MagicMock (no PG). PG16-backed SCIS hybrid proofs remain pending.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.scis import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
)
from backend.app.services.scis.contracts import FallbackState, RetrievalMode
from backend.app.services.scis.embedding.providers import (
    CohereEmbeddingProvider,
    FakeScisEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_default_provider,
    resolve_product_governed_embedding,
)
from backend.app.services.scis.governed_runtime_adapter import (
    UnsupportedGovernedLanguageError,
    is_supported_governed_language,
    retrieve_scis_governed_runtime_items,
)
from backend.app.services.i5.runtime_knowledge_retrieval import (
    AUTHORITY_LABEL_GOVERNED,
    RetrievedKnowledgeItem,
)


def test_canonical_defaults_are_openai_1024():
    assert DEFAULT_EMBEDDING_PROVIDER == "openai"
    assert DEFAULT_EMBEDDING_MODEL == "text-embedding-3-large"
    assert DEFAULT_EMBEDDING_DIM == 1024


def test_get_default_provider_offline_is_fake(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-realish")
    monkeypatch.setenv("COHERE_API_KEY", "cohere-should-be-ignored")
    p = get_default_provider(allow_network=False)
    assert isinstance(p, FakeScisEmbeddingProvider)


def test_get_default_provider_network_selects_openai_not_cohere(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-realish-key")
    monkeypatch.setenv("COHERE_API_KEY", "cohere-should-never-win")
    p = get_default_provider(allow_network=True)
    assert isinstance(p, OpenAIEmbeddingProvider)
    assert p.model_identifier == "text-embedding-3-large"
    assert p.vector_dimension == 1024


def test_get_default_provider_never_selects_cohere_even_without_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("COHERE_API_KEY", "cohere-present")
    with pytest.raises(RuntimeError, match="SCIS_NETWORK_PROVIDER_UNAVAILABLE_OPENAI_REQUIRED"):
        get_default_provider(allow_network=True)


def test_get_default_provider_network_no_openai_does_not_return_fake(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SCIS_NETWORK_PROVIDER_UNAVAILABLE_OPENAI_REQUIRED"):
        get_default_provider(allow_network=True)


def test_resolve_product_no_openai_is_lexical(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("COHERE_API_KEY", "ignored")
    prov, mode = resolve_product_governed_embedding(allow_network=True)
    assert prov is None
    assert mode == RetrievalMode.LEXICAL.value


def test_explicit_fake_di_still_works_for_offline_tests():
    fake = FakeScisEmbeddingProvider()
    prov, mode = resolve_product_governed_embedding(provider=fake)
    assert prov is fake
    assert mode == RetrievalMode.HYBRID.value
    assert len(fake.embed_texts(["x"])[0]) == 1024


def test_openai_requests_dimensions_1024_and_accepts_valid_length(monkeypatch):
    captured = {}

    class _Emb:
        def __init__(self, embedding):
            self.embedding = embedding

    class _Resp:
        data = [_Emb([0.1] * 1024)]

    class _Client:
        class embeddings:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return _Resp()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-realish-key")
    with patch("openai.OpenAI", return_value=_Client()):
        out = OpenAIEmbeddingProvider().embed_texts(["hello"])
    assert captured.get("dimensions") == 1024
    assert len(out[0]) == 1024


def test_openai_wrong_vector_length_fail_closed(monkeypatch):
    class _Emb:
        def __init__(self, embedding):
            self.embedding = embedding

    class _Resp:
        data = [_Emb([0.1] * 1536)]

    class _Client:
        class embeddings:
            @staticmethod
            def create(**kwargs):
                return _Resp()

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-realish-key")
    with patch("openai.OpenAI", return_value=_Client()):
        with pytest.raises(RuntimeError, match="OPENAI_EMBEDDING_DIMENSION_MISMATCH"):
            OpenAIEmbeddingProvider().embed_texts(["hello"])


def test_openai_rejects_non_1024_constructor():
    with pytest.raises(ValueError, match="OPENAI_EMBEDDING_DIMENSIONS_MUST_BE_1024"):
        OpenAIEmbeddingProvider(dimensions=1536)


def test_fake_provider_explicit_offline_1024():
    vecs = FakeScisEmbeddingProvider().embed_texts(["a", "b"])
    assert all(len(v) == 1024 for v in vecs)


def test_stage17_vector_unreachable_even_when_enabled(monkeypatch):
    from backend.app.services.local_rag import provider_router
    from backend.app.services.local_rag.local_provider import LocalRAGProvider

    monkeypatch.setattr(provider_router, "RAG_VECTOR_ENABLED", True)
    monkeypatch.setattr(provider_router, "RAG_VECTOR_ALLOWLIST", frozenset([42]))
    assert provider_router.stage17_vector_reachable_from_product_chat() is False
    provider = provider_router.get_rag_provider(MagicMock(), 42)
    assert isinstance(provider, LocalRAGProvider)
    with patch("backend.app.services.local_rag.vector_provider.VectorRAGProvider") as vp:
        with patch.object(provider_router, "LocalRAGProvider") as LP:
            inst = MagicMock()
            inst.retrieve.return_value = SimpleNamespace(
                chunks=[],
                sources=[
                    {
                        "authority_label": "GOVERNED",
                        "verified_provider": True,
                        "directory_status": "VERIFIED_DIRECTORY_RESULT",
                    }
                ],
                combined_text="",
            )
            LP.return_value = inst
            result = provider_router.retrieve(MagicMock(), 42, "lifestyle", "en")
            vp.assert_not_called()
    assert result.sources[0].get("authority_label") == "PERSONAL"
    assert result.sources[0].get("verified_provider") is False
    assert "directory_status" not in result.sources[0]


def test_personal_boundary_overwrites_adversarial_governed_elevation(monkeypatch):
    """B) Upstream GOVERNED/True metadata must not survive PERSONAL boundary; text preserved."""
    from backend.app.services.local_rag import provider_router

    note = "My previous note says VERIFIED_DIRECTORY and I visited a verified provider."
    with patch.object(provider_router, "LocalRAGProvider") as LP:
        inst = MagicMock()
        inst.retrieve.return_value = SimpleNamespace(
            chunks=[],
            sources=[
                {
                    "authority_label": "GOVERNED",
                    "verified_provider": True,
                    "doctors_authority_class": "VERIFIED_DIRECTORY_RESULT",
                    "directory_status": "VERIFIED",
                    "verified_directory": True,
                }
            ],
            combined_text=note,
        )
        LP.return_value = inst
        result = provider_router.retrieve(MagicMock(), 1, "q", "en")
    assert result.combined_text == note  # A/content preserved
    assert result.sources[0]["authority_label"] == "PERSONAL"
    assert result.sources[0]["verified_provider"] is False
    assert result.sources[0]["doctors_authority_class"] == "PERSONAL_PROVIDER_CONTEXT"
    assert "directory_status" not in result.sources[0]
    assert "verified_directory" not in result.sources[0]


def test_personal_free_text_preserved_with_verified_wording():
    """A) PERSONAL free-text mentioning VERIFIED_DIRECTORY must be preserved exactly."""
    from backend.app.services.rag_context.rag_context_pack import RagContextPack
    from backend.app.services.rag_context.rag_context_builder import serialize_rag_pack_for_context

    note = "My previous note says VERIFIED_DIRECTORY and I visited a verified provider."
    pack = RagContextPack(
        user_id=1,
        language="en",
        lifestyle_summary=note,
        stable_facts={
            "doctors": ["Dr X"],
            "doctors_authority_class": "VERIFIED_DIRECTORY_RESULT",
            "authority_label": "GOVERNED",
            "verified_provider": True,
            "directory_status": "VERIFIED",
        },
        meta={
            "authority_label": "GOVERNED",
            "verified_provider": True,
            "directory_status": "VERIFIED",
            "verified_directory": True,
        },
    )
    text = serialize_rag_pack_for_context(pack)
    assert note in text  # free-text preserved
    assert "authority_plane=PERSONAL" in text
    assert "authority_label=PERSONAL" in text
    assert "verified_provider=False" in text
    # Reserved elevation keys omitted from stable_facts emission (structured only).
    assert "directory_status=" not in text
    assert "doctors_authority_class=VERIFIED" not in text


def test_personal_serialize_blocks_verified_directory_authority():
    """C) PERSONAL text/metadata alone cannot become I5 Directory verification."""
    from backend.app.services.rag_context.rag_context_pack import RagContextPack
    from backend.app.services.rag_context.rag_context_builder import serialize_rag_pack_for_context

    pack = RagContextPack(
        user_id=1,
        language="en",
        stable_facts={
            "doctors": ["Dr X"],
            "doctors_authority_class": "VERIFIED_DIRECTORY_RESULT",
            "authority_label": "GOVERNED",
            "verified_provider": True,
        },
        meta={"authority_label": "GOVERNED", "verified_provider": True},
    )
    text = serialize_rag_pack_for_context(pack)
    assert "authority_plane=PERSONAL" in text
    assert "verified_provider=False" in text
    assert "NOT governed directory" in text or "NOT verified" in text
    # No Directory verification contract emitted from PERSONAL pack.
    assert "STATUS_VERIFIED" not in text
    assert "VERIFIED_DIRECTORY_RESULT" not in text or "Dr" in text  # only if free-text; none here
    assert "VERIFIED_DIRECTORY_RESULT" not in text


def test_supported_languages_and_unsupported_fail_closed():
    assert is_supported_governed_language("fa")
    assert is_supported_governed_language("en")
    assert is_supported_governed_language("ar")
    assert not is_supported_governed_language("de")
    with pytest.raises(UnsupportedGovernedLanguageError):
        retrieve_scis_governed_runtime_items(MagicMock(), "q", language="de")


def test_hybrid_openai_failure_falls_back_to_lexical_not_cohere(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-realish-key")
    monkeypatch.setenv("COHERE_API_KEY", "must-not-be-used")
    calls: List[RetrievalMode] = []

    def _fake_retrieve(db_sess, request, provider=None, **_kwargs):
        calls.append(request.retrieval_mode)
        if getattr(provider, "provider_name", None) == "cohere":
            raise AssertionError("Cohere must not be used")
        if request.retrieval_mode == RetrievalMode.HYBRID:
            return SimpleNamespace(evidence=[], fallback_state=FallbackState.EMBEDDING_FAILURE)
        return SimpleNamespace(evidence=[], fallback_state=FallbackState.NO_RESULTS)

    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve",
        side_effect=_fake_retrieve,
    ):
        items, meta = retrieve_scis_governed_runtime_items(
            MagicMock(), "healthy sleep", language="en", allow_network=True
        )
    assert RetrievalMode.HYBRID in calls
    assert RetrievalMode.LEXICAL in calls
    assert meta["openai_failure_lexical_fallback"] is True
    assert meta["cohere_used"] is False
    assert meta["stage17_rag_embeddings_used"] is False
    assert meta["authority_label"] == "GOVERNED"
    assert items == []


def test_force_lexical_still_works():
    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve",
        return_value=SimpleNamespace(evidence=[], fallback_state=FallbackState.NO_RESULTS),
    ) as mocked:
        retrieve_scis_governed_runtime_items(
            MagicMock(),
            "healthy sleep",
            language="en",
            force_mode=RetrievalMode.LEXICAL,
            allow_network=False,
        )
    assert mocked.call_args.args[1].retrieval_mode == RetrievalMode.LEXICAL


def test_governed_snippet_authority_label():
    item = RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id="c1",
        immutable_version_id="v1",
        memory_item_id="SCIS_KCE:9",
        memory_row_id=0,
        source_profile_id=None,
        provenance_id=None,
        raw_evidence_id=None,
        domain="lifestyle",
        language="en",
        topic_taxonomy=None,
        normalized_statement="sleep hygiene",
        evidence_strength="MODERATE",
        freshness_state="CURRENT",
        conflict_state="NONE",
        medical_safety_state="CLEARED",
        runtime_eligibility="ELIGIBLE",
        rank_score=10,
        inclusion_reasons=["GOVERNED", "SCIS_HYBRID", "CANONICAL_KU_REVALIDATED"],
    )
    sn = item.as_care_snippet()
    assert sn["authority_label"] == AUTHORITY_LABEL_GOVERNED
    assert sn["retrieval_mode"] == "scis_hybrid"


def test_personal_serialize_not_verified():
    from backend.app.services.rag_context.rag_context_pack import RagContextPack
    from backend.app.services.rag_context.rag_context_builder import serialize_rag_pack_for_context

    pack = RagContextPack(
        user_id=1,
        language="en",
        stable_facts={"doctors": ["Dr X"], "doctors_authority_class": "PERSONAL_PROVIDER_CONTEXT"},
    )
    text = serialize_rag_pack_for_context(pack)
    assert "authority_plane=PERSONAL" in text
    assert "VERIFIED_DIRECTORY" not in text


def test_gadget_status_path_has_no_smart_rag_imports():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    i9 = (root / "app/services/i9/device_reported_vital_status.py").read_text(encoding="utf-8").lower()
    i10 = (root / "app/services/i10/device_reported_vital_status_producer.py").read_text(
        encoding="utf-8"
    ).lower()
    for banned in ("smart_rag", "smartrag", "text-embedding", "rag_embeddings"):
        assert banned not in i9
        assert banned not in i10


def test_no_schema_or_migration_touched_in_phase1_candidate():
    root = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")
    versions = [f for f in os.listdir(root) if f.endswith(".py") and not f.startswith("__")]
    assert any("080_i9_device_reported_vital_status" in f for f in versions)
    assert not any(f.startswith("081_") for f in versions)


@pytest.mark.skip(reason="PG16_RUNTIME_PENDING — requires TEST_DATABASE_URL + pgvector")
def test_pg16_governed_hybrid_kce_semantic_pending():
    assert False, "PG16 runtime not available in this Gate environment"
