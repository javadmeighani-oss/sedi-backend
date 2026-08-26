"""I5 RSS_OR_FEED adapter — fixture + controlled live HTTPS RSS/Atom."""
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

ADAPTER_ID = "i5.rss_feed"
ADAPTER_VERSION = "fmt-resilience-v1"

_ALLOWED_TYPES = frozenset(
    {
        "application/rss+xml",
        "application/atom+xml",
        "application/xml",
        "text/xml",
    }
)


def _assert_feed_envelope(envelope: FetchEnvelope) -> None:
    if envelope.error_category is not None:
        return
    low = (envelope.body or b"")[:800].lower()
    if b"<rss" not in low and b"<feed" not in low:
        raise AdapterFrameworkError("INVALID_CONTENT_TYPE", "NOT_RSS_ATOM")
    if envelope.content_type not in _ALLOWED_TYPES:
        # Generic XML MIME ok when feed markers present
        if envelope.content_type not in {"application/xml", "text/xml", "application/octet-stream"}:
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", envelope.content_type)


class RssFeedAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            mode="RSS_OR_FEED",
            capabilities=(
                "FETCH",
                "EXTRACTION",
                "CONTENT_TYPES",
                "PAGINATION",
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
        if envelope.error_category is None and envelope.content_type not in _ALLOWED_TYPES:
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", envelope.content_type)
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
        _assert_feed_envelope(envelope)
        return envelope
