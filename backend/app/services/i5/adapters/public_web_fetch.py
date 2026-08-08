"""I5-IMPL-W3-P01/W6-P01 — PUBLIC_WEB_FETCH adapter.

`fetch_fixture` wraps the Gate3 fetcher symbol and remains fixture-only (no
live network). `fetch_live` (W6-P01) is the only adapter method in this
package that may perform a real HTTPS request — it is a thin governance +
envelope wrapper around `adapters.live_transport.fetch_live_https`.
OFFICIAL_API / RSS_OR_FEED adapters intentionally remain fixture-only.
"""
from __future__ import annotations

from typing import Optional, Sequence

from backend.app.schemas.i5_adapters import AdapterMetadata, FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CONTENT_BYTES,
    FixtureTransport,
    SourceAdapter,
    assert_source_governance_allows_controlled_use,
    build_fetch_envelope,
    public_web_fetcher_substrate_symbol,
)
from backend.app.services.i5.adapters.live_transport import HttpGet, fetch_live_https

ADAPTER_ID = "i5.public_web_fetch"
ADAPTER_VERSION = "1.0.0"


class PublicWebFetchAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            mode="PUBLIC_WEB_FETCH",
            capabilities=(
                "FETCH",
                "EXTRACTION",
                "CONTENT_TYPES",
                "LANGUAGE_SUPPORT",
                "CONDITIONAL_FETCH",
            ),
        )

    def substrate(self) -> str:
        return public_web_fetcher_substrate_symbol()

    def fetch_fixture(
        self,
        *,
        request_id: str,
        url: str,
        transport: FixtureTransport,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = 2_097_152,
    ) -> FetchEnvelope:
        assert_source_governance_allows_controlled_use(governance)
        response = transport(url)
        return build_fetch_envelope(
            request_id=request_id,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            url=url,
            response=response,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )

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
        """Controlled live HTTPS fetch (W6-P01). Governance gate, then live
        transport, then the unchanged `build_fetch_envelope` pipeline —
        identical envelope shape/classification to `fetch_fixture`.
        """
        assert_source_governance_allows_controlled_use(governance)
        response = fetch_live_https(
            url=url,
            allowed_domain=governance.allowed_domain or "",
            allowed_url_patterns=allowed_url_patterns,
            trust_level=trust_level,
            review_required=review_required,
            max_bytes=max_bytes,
            timeout=timeout,
            http_get=http_get,
        )
        return build_fetch_envelope(
            request_id=request_id,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
            url=url,
            response=response,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )
