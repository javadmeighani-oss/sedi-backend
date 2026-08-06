"""I5-IMPL-W3-P01 — PUBLIC_WEB_FETCH adapter (wraps Gate3 fetcher symbol; fixture-only)."""
from __future__ import annotations

from backend.app.schemas.i5_adapters import AdapterMetadata, FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    FixtureTransport,
    SourceAdapter,
    assert_source_governance_allows_controlled_use,
    build_fetch_envelope,
    public_web_fetcher_substrate_symbol,
)

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
