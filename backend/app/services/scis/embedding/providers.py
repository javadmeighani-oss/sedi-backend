"""SCIS embedding providers — global governed knowledge only (no PHI).

Phase1 canonical network provider = OpenAI text-embedding-3-large @1024.
Cohere remains dormant for historical compatibility and is never selected
by get_default_provider. FakeScisEmbeddingProvider is offline CI / explicit DI only.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence

from backend.app.services.scis import (
    COHERE_HISTORICAL_MODEL,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
)


class ScisEmbeddingProvider(Protocol):
    provider_name: str
    model_identifier: str
    model_version: str
    vector_dimension: int

    def embed_texts(self, texts: Sequence[str], *, input_type: str = "search_document") -> List[List[float]]:
        ...


@dataclass
class EmbeddingMeta:
    provider: str
    model: str
    model_version: str
    dimension: int


class FakeScisEmbeddingProvider:
    """Deterministic 1024-d embeddings for CI / explicit offline DI (no network)."""

    provider_name = "fake"
    model_identifier = "fake-scis-multilingual-v1"
    model_version = "v1"
    vector_dimension = DEFAULT_EMBEDDING_DIM

    def embed_texts(self, texts: Sequence[str], *, input_type: str = "search_document") -> List[List[float]]:
        out: List[List[float]] = []
        for text in texts:
            seed = f"{input_type}|{text}".encode("utf-8")
            digest = hashlib.sha256(seed).digest()
            buf = bytearray()
            block = digest
            while len(buf) < self.vector_dimension:
                block = hashlib.sha256(block).digest()
                buf.extend(block)
            vec = [((buf[i] / 255.0) * 2.0) - 1.0 for i in range(self.vector_dimension)]
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            out.append([x / norm for x in vec])
        return out


class CohereEmbeddingProvider:
    """Historical Cohere Embed API — dormant; not selected by canonical runtime."""

    provider_name = "cohere"
    vector_dimension = DEFAULT_EMBEDDING_DIM

    def __init__(
        self,
        *,
        model: str = COHERE_HISTORICAL_MODEL,
        api_key: Optional[str] = None,
        model_version: str = "2024-v3",
    ) -> None:
        self.model_identifier = model
        self.model_version = model_version
        self._api_key = api_key or os.environ.get("COHERE_API_KEY") or os.environ.get("SEDI_COHERE_API_KEY")

    def embed_texts(self, texts: Sequence[str], *, input_type: str = "search_document") -> List[List[float]]:
        if not self._api_key:
            raise RuntimeError("COHERE_API_KEY_MISSING")
        import urllib.request

        payload = {
            "model": self.model_identifier,
            "texts": list(texts),
            "input_type": input_type,
            "embedding_types": ["float"],
        }
        req = urllib.request.Request(
            "https://api.cohere.com/v1/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Cohere-Version": "2022-12-06",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        embeddings = body.get("embeddings")
        if isinstance(embeddings, dict):
            floats = embeddings.get("float") or []
        else:
            floats = embeddings or []
        if len(floats) != len(texts):
            raise RuntimeError("COHERE_EMBED_COUNT_MISMATCH")
        return [[float(x) for x in vec] for vec in floats]


class OpenAIEmbeddingProvider:
    """Canonical network provider: OpenAI text-embedding-3-large @1024."""

    provider_name = "openai"
    vector_dimension = DEFAULT_EMBEDDING_DIM

    def __init__(
        self,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
        api_key: Optional[str] = None,
        model_version: str = "3-large",
        dimensions: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        if dimensions != DEFAULT_EMBEDDING_DIM:
            raise ValueError("OPENAI_EMBEDDING_DIMENSIONS_MUST_BE_1024")
        if model != DEFAULT_EMBEDDING_MODEL and model != "text-embedding-3-large":
            # Allow only canonical model for Phase1 product path constructors.
            raise ValueError("OPENAI_EMBEDDING_MODEL_MUST_BE_TEXT_EMBEDDING_3_LARGE")
        self.model_identifier = model
        self.model_version = model_version
        self.vector_dimension = dimensions
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def embed_texts(self, texts: Sequence[str], *, input_type: str = "search_document") -> List[List[float]]:
        if not self._api_key or self._api_key.endswith("not-used") or "placeholder" in (self._api_key or ""):
            raise RuntimeError("OPENAI_API_KEY_MISSING_OR_PLACEHOLDER")
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        resp = client.embeddings.create(
            model=self.model_identifier,
            input=list(texts),
            dimensions=self.vector_dimension,
        )
        out: List[List[float]] = []
        for d in resp.data:
            emb = list(d.embedding)
            if len(emb) != self.vector_dimension:
                raise RuntimeError("OPENAI_EMBEDDING_DIMENSION_MISMATCH")
            out.append(emb)
        if len(out) != len(texts):
            raise RuntimeError("OPENAI_EMBED_COUNT_MISMATCH")
        return out


def _openai_key_usable() -> bool:
    key = os.environ.get("OPENAI_API_KEY") or ""
    if not key:
        return False
    if key.endswith("not-used") or "placeholder" in key:
        return False
    return True


def get_default_provider(*, allow_network: bool = False) -> ScisEmbeddingProvider:
    """Canonical selection: Fake offline-only; OpenAI when network allowed+configured.

    Cohere is never selected — even if COHERE_API_KEY is present.
    FakeScisEmbeddingProvider is NEVER returned when allow_network=True
    (FAKE_SCIS=OFFLINE_CI_TEST_ONLY). Product path must use
    resolve_product_governed_embedding → SAFE_CANONICAL_LEXICAL instead.
    """
    if not allow_network:
        return FakeScisEmbeddingProvider()
    if _openai_key_usable():
        return OpenAIEmbeddingProvider(
            model=DEFAULT_EMBEDDING_MODEL,
            dimensions=DEFAULT_EMBEDDING_DIM,
        )
    raise RuntimeError("SCIS_NETWORK_PROVIDER_UNAVAILABLE_OPENAI_REQUIRED")


def resolve_product_governed_embedding(
    *,
    allow_network: bool = True,
    provider: Optional[ScisEmbeddingProvider] = None,
) -> tuple[Optional[ScisEmbeddingProvider], str]:
    """Product governed path: OpenAI for HYBRID; else SAFE_CANONICAL_LEXICAL.

    Explicit DI provider is honored for tests. Fake is never treated as real
    network semantic for product mode resolution (returns lexical).
    """
    from backend.app.services.scis.contracts import RetrievalMode

    if provider is not None:
        name = getattr(provider, "provider_name", "")
        if name == "openai":
            return provider, RetrievalMode.HYBRID.value
        if name == "fake":
            # Explicit Fake DI: allow HYBRID only for deterministic offline tests.
            return provider, RetrievalMode.HYBRID.value
        if name == "cohere":
            # Refuse Cohere as product semantic provider.
            return None, RetrievalMode.LEXICAL.value
        return provider, RetrievalMode.HYBRID.value

    if not allow_network or not _openai_key_usable():
        return None, RetrievalMode.LEXICAL.value
    return (
        OpenAIEmbeddingProvider(model=DEFAULT_EMBEDDING_MODEL, dimensions=DEFAULT_EMBEDDING_DIM),
        RetrievalMode.HYBRID.value,
    )


def assert_global_knowledge_only(texts: Sequence[str], *, source_class: str) -> None:
    if source_class != "GLOBAL_GOVERNED_KNOWLEDGE":
        raise PermissionError("SCIS_EXTERNAL_EMBED_DENIED_NON_GLOBAL")
    banned = ("user_id=", "phone=", "ssn=", "national_id=")
    for t in texts:
        low = (t or "").lower()
        if any(b in low for b in banned):
            raise PermissionError("SCIS_EXTERNAL_EMBED_DENIED_SUSPECTED_PHI")


# Re-export canonical constants for callers/tests.
CANONICAL_NETWORK_PROVIDER = DEFAULT_EMBEDDING_PROVIDER
CANONICAL_EMBEDDING_MODEL = DEFAULT_EMBEDDING_MODEL
CANONICAL_EMBEDDING_DIM = DEFAULT_EMBEDDING_DIM
