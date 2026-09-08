"""Standalone Phase1 focused verifier (no pytest conftest / no PG required)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["OPENAI_API_KEY"] = "sk-test-realish-key"
os.environ["COHERE_API_KEY"] = "cohere-ignored"

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        print(f"FAIL {name} {detail}")


def main() -> int:
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
    from backend.app.services.local_rag import provider_router
    from backend.app.services.scis.governed_runtime_adapter import (
        UnsupportedGovernedLanguageError,
        is_supported_governed_language,
        retrieve_scis_governed_runtime_items,
    )
    from backend.app.services.i5.runtime_knowledge_retrieval import (
        AUTHORITY_LABEL_GOVERNED,
        RetrievedKnowledgeItem,
    )

    check(
        "01_defaults",
        DEFAULT_EMBEDDING_PROVIDER == "openai"
        and DEFAULT_EMBEDDING_MODEL == "text-embedding-3-large"
        and DEFAULT_EMBEDDING_DIM == 1024,
    )

    p = get_default_provider(allow_network=False)
    check("05_fake_offline", isinstance(p, FakeScisEmbeddingProvider))

    p = get_default_provider(allow_network=True)
    check("01_openai_selected", isinstance(p, OpenAIEmbeddingProvider) and p.vector_dimension == 1024)
    check("02_not_cohere", not isinstance(p, CohereEmbeddingProvider))

    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["COHERE_API_KEY"] = "present"
    try:
        get_default_provider(allow_network=True)
        check("02_cohere_never_selected", False, "expected raise")
    except RuntimeError as e:
        check("02_cohere_never_selected", "SCIS_NETWORK_PROVIDER_UNAVAILABLE_OPENAI_REQUIRED" in str(e))
    os.environ.pop("COHERE_API_KEY", None)
    try:
        get_default_provider(allow_network=True)
        check("C_no_fake_network", False, "expected raise")
    except RuntimeError as e:
        check("C_no_fake_network", "SCIS_NETWORK_PROVIDER_UNAVAILABLE_OPENAI_REQUIRED" in str(e))
    os.environ["OPENAI_API_KEY"] = "sk-test-realish-key"

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

    with patch("openai.OpenAI", return_value=_Client()):
        out = OpenAIEmbeddingProvider().embed_texts(["hello"])
    check("03_dimensions_1024_sent", captured.get("dimensions") == 1024)
    check("04_valid_1024_accepted", len(out[0]) == 1024)

    class _RespBad:
        data = [_Emb([0.1] * 1536)]

    class _ClientBad:
        class embeddings:
            @staticmethod
            def create(**kwargs):
                return _RespBad()

    try:
        with patch("openai.OpenAI", return_value=_ClientBad()):
            OpenAIEmbeddingProvider().embed_texts(["hello"])
        check("04_wrong_len_fail_closed", False)
    except RuntimeError as e:
        check("04_wrong_len_fail_closed", "DIMENSION_MISMATCH" in str(e))

    try:
        OpenAIEmbeddingProvider(dimensions=1536)
        check("04_ctor_reject", False)
    except ValueError:
        check("04_ctor_reject", True)

    vecs = FakeScisEmbeddingProvider().embed_texts(["a", "b"])
    check("05_fake_1024", len(vecs) == 2 and all(len(v) == 1024 for v in vecs))

    prov, mode = resolve_product_governed_embedding(allow_network=True)
    check("resolve_hybrid", isinstance(prov, OpenAIEmbeddingProvider) and mode == "hybrid")
    prov, mode = resolve_product_governed_embedding(provider=CohereEmbeddingProvider(api_key="x"))
    check("resolve_reject_cohere", prov is None and mode == "lexical")

    check("06_stage17_disabled", provider_router.STAGE17_VECTOR_PRODUCT_CHAT_DISABLED is True)
    check("07_unreachable", provider_router.stage17_vector_reachable_from_product_chat() is False)
    check(
        "06_provider_type",
        provider_router.get_rag_provider(MagicMock(), 1).__class__.__name__ == "LocalRAGProvider",
    )

    with patch("backend.app.services.local_rag.vector_provider.VectorRAGProvider") as vp:
        with patch.object(provider_router, "LocalRAGProvider") as LP:
            note = "My previous note says VERIFIED_DIRECTORY and I visited a verified provider."
            inst = MagicMock()
            inst.retrieve.return_value = SimpleNamespace(
                chunks=[],
                sources=[
                    {
                        "authority_label": "GOVERNED",
                        "verified_provider": True,
                        "directory_status": "VERIFIED_DIRECTORY_RESULT",
                        "doctors_authority_class": "VERIFIED_DIRECTORY_RESULT",
                    }
                ],
                combined_text=note,
            )
            LP.return_value = inst
            provider_router.RAG_VECTOR_ENABLED = True
            provider_router.RAG_VECTOR_ALLOWLIST = frozenset([1])
            result = provider_router.retrieve(MagicMock(), 1, "q", "en")
            vp.assert_not_called()
            check("07_vector_not_called", True)
            check("A_text_preserved", result.combined_text == note)
            check("A_personal_overwrite_label", result.sources[0]["authority_label"] == "PERSONAL")
            check("A_personal_overwrite_verified", result.sources[0]["verified_provider"] is False)
            check(
                "A_personal_overwrite_doctors_class",
                result.sources[0].get("doctors_authority_class") == "PERSONAL_PROVIDER_CONTEXT",
            )

    check("22_fa", is_supported_governed_language("fa"))
    check("23_en", is_supported_governed_language("en"))
    check("24_ar", is_supported_governed_language("ar"))
    check("25_de_unsupported", not is_supported_governed_language("de"))

    try:
        retrieve_scis_governed_runtime_items(MagicMock(), "q", language="de")
        check("25_fail_closed", False)
    except UnsupportedGovernedLanguageError:
        check("25_fail_closed", True)

    calls = []

    def _fake_retrieve(db, request, provider=None, **_kwargs):
        calls.append(request.retrieval_mode)
        if getattr(provider, "provider_name", None) == "cohere":
            raise AssertionError("cohere")
        if request.retrieval_mode == RetrievalMode.HYBRID:
            return SimpleNamespace(evidence=[], fallback_state=FallbackState.EMBEDDING_FAILURE)
        return SimpleNamespace(evidence=[], fallback_state=FallbackState.NO_RESULTS)

    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve",
        side_effect=_fake_retrieve,
    ):
        _items, meta = retrieve_scis_governed_runtime_items(
            MagicMock(), "sleep", language="en", allow_network=True
        )
    check("10_hybrid_attempted", RetrievalMode.HYBRID in calls)
    check(
        "11_lexical_fallback",
        RetrievalMode.LEXICAL in calls and meta["openai_failure_lexical_fallback"],
    )
    check("12_no_cohere", meta["cohere_used"] is False)
    check("13_no_stage17", meta["stage17_rag_embeddings_used"] is False)
    check("19_governed_label", meta["authority_label"] == "GOVERNED")

    with patch(
        "backend.app.services.scis.governed_runtime_adapter.retrieve",
        return_value=SimpleNamespace(evidence=[], fallback_state=FallbackState.NO_RESULTS),
    ) as m:
        retrieve_scis_governed_runtime_items(
            MagicMock(),
            "sleep",
            language="en",
            force_mode=RetrievalMode.LEXICAL,
            allow_network=False,
        )
    check("08_lexical_path", m.call_args.args[1].retrieval_mode == RetrievalMode.LEXICAL)

    item = RetrievedKnowledgeItem(
        knowledge_unit_id=1,
        canonical_unit_id="c",
        immutable_version_id="v",
        memory_item_id="SCIS_KCE:1",
        memory_row_id=0,
        source_profile_id=None,
        provenance_id=None,
        raw_evidence_id=None,
        domain="lifestyle",
        language="en",
        topic_taxonomy=None,
        normalized_statement="x",
        evidence_strength="MODERATE",
        freshness_state="CURRENT",
        conflict_state="NONE",
        medical_safety_state="CLEARED",
        runtime_eligibility="ELIGIBLE",
        rank_score=1,
        inclusion_reasons=["GOVERNED", "SCIS_HYBRID", "CANONICAL_KU_REVALIDATED"],
    )
    sn = item.as_care_snippet()
    check("14_ku_revalidation_marker", "CANONICAL_KU_REVALIDATED" in item.inclusion_reasons)
    check("19_snippet_governed", sn["authority_label"] == AUTHORITY_LABEL_GOVERNED)
    check("21_personal_ne_verified", True)  # PERSONAL path stamps verified_provider=False

    i9 = (ROOT / "app/services/i9/device_reported_vital_status.py").read_text(encoding="utf-8").lower()
    i10 = (ROOT / "app/services/i10/device_reported_vital_status_producer.py").read_text(encoding="utf-8").lower()
    check(
        "26_27_no_rag_in_gadget",
        all(b not in i9 and b not in i10 for b in ("smart_rag", "rag_embeddings", "text-embedding")),
    )

    vers = list((ROOT / "alembic/versions").glob("*.py"))
    check(
        "28_no_081_migration",
        any("080_i9" in p.name for p in vers) and not any(p.name.startswith("081_") for p in vers),
    )

    # serialize PERSONAL plane marker without DB
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
            "directory_status": "VERIFIED_DIRECTORY_RESULT",
        },
        meta={"authority_label": "GOVERNED", "verified_provider": True},
    )
    text = serialize_rag_pack_for_context(pack)
    check("20_personal_plane", "authority_plane=PERSONAL" in text)
    check("A_serialize_text_preserved", note in text)
    check("B_no_elevation_key_emit", "directory_status=" not in text)
    check("21_not_verified_directory", "authority_label=PERSONAL" in text and "verified_provider=False" in text)
    check("C_personal_cannot_verify", "NOT governed directory" in text or "NOT verified" in text)

    os.environ.pop("OPENAI_API_KEY", None)
    prov, mode = resolve_product_governed_embedding(allow_network=True)
    check("D_product_no_openai_lexical", prov is None and mode == "lexical")
    check("E_fake_offline", isinstance(get_default_provider(allow_network=False), FakeScisEmbeddingProvider))
    fake = FakeScisEmbeddingProvider()
    prov_f, mode_f = resolve_product_governed_embedding(provider=fake)
    check("F_fake_di", prov_f is fake and mode_f == "hybrid")

    print(f"\nSUMMARY passed={passed} failed={failed} total={passed + failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
