"""SCIS embedding providers — global governed knowledge only (no PHI).

Phase1 canonical network provider = OpenAI text-embedding-3-large @1024.
Phase2-C CASE23: bounded timeout / retry / budget on OpenAI only.
Cohere remains dormant for historical compatibility and is never selected
by get_default_provider. FakeScisEmbeddingProvider is offline CI / explicit DI only.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence

from backend.app.services.scis import (
    COHERE_HISTORICAL_MODEL,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_EMBEDDING_PROVIDER,
)

# CASE23 operational bounds (safety — not a fabricated product SLA).
OPENAI_EMBED_TIMEOUT_SECONDS = 30.0
OPENAI_EMBED_MAX_ATTEMPTS = 3  # 1 initial + 2 retries
OPENAI_EMBED_RETRY_BUDGET_SECONDS = 90.0
OPENAI_EMBED_RETRY_BACKOFF_SECONDS = 0.05  # tiny deterministic backoff for tests/CI

ERROR_OPENAI_TIMEOUT = "OPENAI_TIMEOUT"
ERROR_OPENAI_TRANSIENT = "OPENAI_TRANSIENT"
ERROR_OPENAI_NON_RETRYABLE = "OPENAI_NON_RETRYABLE"
ERROR_OPENAI_RETRY_EXHAUSTED = "OPENAI_RETRY_EXHAUSTED"
ERROR_OPENAI_KEY = "OPENAI_API_KEY_MISSING_OR_PLACEHOLDER"
ERROR_OPENAI_DIMENSION_MISMATCH = "OPENAI_EMBEDDING_DIMENSION_MISMATCH"
ERROR_OPENAI_COUNT_MISMATCH = "OPENAI_EMBED_COUNT_MISMATCH"


class OpenAIEmbeddingFailure(RuntimeError):
    """Bounded, sanitized OpenAI failure — never carries raw HTTP/exception bodies."""

    def __init__(self, error_class: str) -> None:
        self.error_class = str(error_class)
        super().__init__(self.error_class)


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
    network_call_count = 0

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
    network_call_count = 0

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
        self.network_call_count = 0

    def embed_texts(self, texts: Sequence[str], *, input_type: str = "search_document") -> List[List[float]]:
        if not self._api_key:
            raise RuntimeError("COHERE_API_KEY_MISSING")
        import urllib.request

        self.network_call_count += 1
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


def _classify_openai_exception(exc: BaseException) -> tuple[str, bool]:
    """Return (error_class, retryable). Never includes raw exception body."""
    name = type(exc).__name__
    msg = str(exc).lower()
    # Prefer typed OpenAI SDK names when present; fall back to name heuristics.
    if name in {"APITimeoutError", "TimeoutError"} or "timeout" in name.lower():
        return ERROR_OPENAI_TIMEOUT, True
    if name in {"APIConnectionError", "RateLimitError", "InternalServerError", "APIStatusError"}:
        # 5xx / rate-limit / connection → transient; 4xx non-auth handled below.
        status = getattr(exc, "status_code", None)
        if isinstance(status, int) and 400 <= status < 500 and status != 429:
            return ERROR_OPENAI_NON_RETRYABLE, False
        return ERROR_OPENAI_TRANSIENT, True
    if name in {"AuthenticationError", "PermissionDeniedError", "BadRequestError", "NotFoundError"}:
        return ERROR_OPENAI_NON_RETRYABLE, False
    if "timeout" in msg:
        return ERROR_OPENAI_TIMEOUT, True
    if "rate" in msg or "connection" in msg or "temporarily" in msg:
        return ERROR_OPENAI_TRANSIENT, True
    if "auth" in msg or "api key" in msg or "invalid" in msg:
        return ERROR_OPENAI_NON_RETRYABLE, False
    # Unknown → treat as non-retryable to avoid retry storms.
    return ERROR_OPENAI_NON_RETRYABLE, False


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
        timeout_seconds: float = OPENAI_EMBED_TIMEOUT_SECONDS,
        max_attempts: int = OPENAI_EMBED_MAX_ATTEMPTS,
        retry_budget_seconds: float = OPENAI_EMBED_RETRY_BUDGET_SECONDS,
        sleep_fn=None,
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
        self.timeout_seconds = float(timeout_seconds)
        self.max_attempts = max(1, int(max_attempts))
        self.retry_budget_seconds = float(retry_budget_seconds)
        self._sleep = sleep_fn or time.sleep
        self.network_call_count = 0
        self.last_error_class: Optional[str] = None
        self.last_attempt_count = 0

    def _client(self):
        from openai import OpenAI

        return OpenAI(api_key=self._api_key, timeout=self.timeout_seconds)

    def _one_call(self, texts: Sequence[str]) -> List[List[float]]:
        client = self._client()
        self.network_call_count += 1
        resp = client.embeddings.create(
            model=self.model_identifier,
            input=list(texts),
            dimensions=self.vector_dimension,
        )
        out: List[List[float]] = []
        for d in resp.data:
            emb = list(d.embedding)
            if len(emb) != self.vector_dimension:
                raise OpenAIEmbeddingFailure(ERROR_OPENAI_DIMENSION_MISMATCH)
            out.append(emb)
        if len(out) != len(texts):
            raise OpenAIEmbeddingFailure(ERROR_OPENAI_COUNT_MISMATCH)
        return out

    def embed_texts(self, texts: Sequence[str], *, input_type: str = "search_document") -> List[List[float]]:
        del input_type  # OpenAI embeddings API does not use Cohere-style input_type.
        if not self._api_key or self._api_key.endswith("not-used") or "placeholder" in (self._api_key or ""):
            self.last_error_class = ERROR_OPENAI_KEY
            raise OpenAIEmbeddingFailure(ERROR_OPENAI_KEY)

        started = time.monotonic()
        attempts = 0
        last_class = ERROR_OPENAI_NON_RETRYABLE
        while attempts < self.max_attempts:
            elapsed = time.monotonic() - started
            if attempts > 0 and elapsed >= self.retry_budget_seconds:
                self.last_error_class = ERROR_OPENAI_RETRY_EXHAUSTED
                self.last_attempt_count = attempts
                raise OpenAIEmbeddingFailure(ERROR_OPENAI_RETRY_EXHAUSTED)
            attempts += 1
            self.last_attempt_count = attempts
            try:
                out = self._one_call(texts)
                self.last_error_class = None
                return out
            except OpenAIEmbeddingFailure:
                raise
            except Exception as exc:  # noqa: BLE001 — classify; do not persist raw body
                err_class, retryable = _classify_openai_exception(exc)
                last_class = err_class
                self.last_error_class = err_class
                if not retryable or attempts >= self.max_attempts:
                    break
                elapsed = time.monotonic() - started
                if elapsed >= self.retry_budget_seconds:
                    last_class = ERROR_OPENAI_RETRY_EXHAUSTED
                    self.last_error_class = last_class
                    break
                # Bounded tiny backoff; never infinite.
                self._sleep(OPENAI_EMBED_RETRY_BACKOFF_SECONDS)

        if attempts >= self.max_attempts and last_class in {ERROR_OPENAI_TIMEOUT, ERROR_OPENAI_TRANSIENT}:
            self.last_error_class = ERROR_OPENAI_RETRY_EXHAUSTED
            raise OpenAIEmbeddingFailure(ERROR_OPENAI_RETRY_EXHAUSTED)
        self.last_error_class = last_class
        raise OpenAIEmbeddingFailure(last_class)


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
