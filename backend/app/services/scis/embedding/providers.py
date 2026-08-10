"""SCIS embedding providers — global governed knowledge only (no PHI)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence

from backend.app.services.scis import DEFAULT_EMBEDDING_DIM, DEFAULT_EMBEDDING_MODEL, DEFAULT_EMBEDDING_PROVIDER


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
    """Deterministic 1024-d embeddings for CI (no network)."""

    provider_name = "fake"
    model_identifier = "fake-scis-multilingual-v1"
    model_version = "v1"
    vector_dimension = DEFAULT_EMBEDDING_DIM

    def embed_texts(self, texts: Sequence[str], *, input_type: str = "search_document") -> List[List[float]]:
        out: List[List[float]] = []
        for text in texts:
            seed = f"{input_type}|{text}".encode("utf-8")
            digest = hashlib.sha256(seed).digest()
            # Expand digest to 1024 dims deterministically
            buf = bytearray()
            block = digest
            while len(buf) < self.vector_dimension:
                block = hashlib.sha256(block).digest()
                buf.extend(block)
            vec = [((buf[i] / 255.0) * 2.0) - 1.0 for i in range(self.vector_dimension)]
            # L2 normalize
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            out.append([x / norm for x in vec])
        return out


class CohereEmbeddingProvider:
    """Cohere Embed API — global public text only."""

    provider_name = "cohere"
    vector_dimension = DEFAULT_EMBEDDING_DIM

    def __init__(
        self,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
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

        # Official Embed API — access docs.cohere.com; network only when key present.
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
    """OpenAI text-embedding-3-large @1024 — optional challenger."""

    provider_name = "openai"
    vector_dimension = DEFAULT_EMBEDDING_DIM

    def __init__(
        self,
        *,
        model: str = "text-embedding-3-large",
        api_key: Optional[str] = None,
        model_version: str = "3-large",
        dimensions: int = DEFAULT_EMBEDDING_DIM,
    ) -> None:
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
        return [list(d.embedding) for d in resp.data]


def get_default_provider(*, allow_network: bool = False) -> ScisEmbeddingProvider:
    if not allow_network:
        return FakeScisEmbeddingProvider()
    if os.environ.get("COHERE_API_KEY") or os.environ.get("SEDI_COHERE_API_KEY"):
        return CohereEmbeddingProvider()
    if os.environ.get("OPENAI_API_KEY") and "placeholder" not in os.environ.get("OPENAI_API_KEY", ""):
        return OpenAIEmbeddingProvider()
    return FakeScisEmbeddingProvider()


def assert_global_knowledge_only(texts: Sequence[str], *, source_class: str) -> None:
    if source_class != "GLOBAL_GOVERNED_KNOWLEDGE":
        raise PermissionError("SCIS_EXTERNAL_EMBED_DENIED_NON_GLOBAL")
    # Soft guard: refuse obvious PHI-ish markers in eval fixtures
    banned = ("user_id=", "phone=", "ssn=", "national_id=")
    for t in texts:
        low = (t or "").lower()
        if any(b in low for b in banned):
            raise PermissionError("SCIS_EXTERNAL_EMBED_DENIED_SUSPECTED_PHI")
