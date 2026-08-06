"""I5-IMPL-W3-P01 — OFFICIAL_API adapter (fixture JSON/API envelopes; no live network)."""
from __future__ import annotations

from backend.app.schemas.i5_adapters import AdapterMetadata, FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    FixtureTransport,
    SourceAdapter,
    assert_source_governance_allows_controlled_use,
    build_fetch_envelope,
)

ADAPTER_ID = "i5.official_api"
ADAPTER_VERSION = "1.0.0"


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
        max_bytes: int = 2_097_152,
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
        if envelope.error_category is None and envelope.content_type not in {
            "application/json",
            "application/vnd.api+json",
        }:
            from backend.app.services.i5.adapters.base import AdapterFrameworkError

            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", envelope.content_type)
        return envelope
