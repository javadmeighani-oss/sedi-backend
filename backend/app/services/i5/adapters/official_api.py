"""I5 OFFICIAL_API adapter — fixture + controlled live HTTPS JSON/API."""
from __future__ import annotations

from typing import Optional, Sequence

from backend.app.schemas.i5_adapters import AdapterMetadata, FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CONTENT_BYTES,
    AdapterFrameworkError,
    FixtureTransport,
    SourceAdapter,
    assert_source_governance_allows_controlled_use,
    build_fetch_envelope,
)
from backend.app.services.i5.adapters.live_fetch import fetch_live_envelope
from backend.app.services.i5.adapters.live_transport import HttpGet
from backend.app.services.i5.adapters.representation_classifier import classify_representation

ADAPTER_ID = "i5.official_api"
ADAPTER_VERSION = "fmt-resilience-v1"

_JSON_TYPES = frozenset({"application/json", "application/vnd.api+json", "text/json"})


def _assert_json_envelope(envelope: FetchEnvelope) -> None:
    if envelope.error_category is not None:
        return
    decision = classify_representation(
        content_type=envelope.content_type,
        payload=envelope.body,
    )
    if decision.representation != "JSON":
        raise AdapterFrameworkError("INVALID_CONTENT_TYPE", decision.representation)
    if envelope.content_type not in _JSON_TYPES and not envelope.body.lstrip()[:1] in {b"{", b"["}:
        raise AdapterFrameworkError("INVALID_CONTENT_TYPE", envelope.content_type)


class OfficialApiAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            mode="OFFICIAL_API",
            capabilities=(
                "FETCH",
                "EXTRACTION",
                "CONTENT_TYPES",
                "PAGINATION",
                "CONDITIONAL_FETCH",
            ),
        )

    def fetch_fixture(
        self,
        *,
        request_id: str,
        url: str,
        transport: FixtureTransport,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
    ) -> FetchEnvelope:
        assert_source_governance_allows_controlled_use(governance)
        response = transport(url)
        envelope = build_fetch_envelope(
            request_id=request_id,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            url=url,
            response=response,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )
        _assert_json_envelope(envelope)
        return envelope

    def fetch_live(
        self,
        *,
        request_id: str,
        url: str,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        allowed_url_patterns: Optional[Sequence[str]] = None,
        trust_level: str = "official",
        review_required: bool = True,
        http_get: Optional[HttpGet] = None,
    ) -> FetchEnvelope:
        envelope = fetch_live_envelope(
            request_id=request_id,
            url=url,
            governance=governance,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            max_bytes=max_bytes,
            timeout=timeout,
            allowed_url_patterns=allowed_url_patterns,
            trust_level=trust_level,
            review_required=review_required,
            http_get=http_get,
        )
        _assert_json_envelope(envelope)
        return envelope
