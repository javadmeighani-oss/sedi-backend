"""Shared controlled live HTTPS fetch helper for all I5 format adapters."""
from __future__ import annotations

from typing import Optional, Sequence

from backend.app.schemas.i5_adapters import FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CONTENT_BYTES,
    assert_source_governance_allows_controlled_use,
    build_fetch_envelope,
)
from backend.app.services.i5.adapters.live_transport import HttpGet, fetch_live_https


def fetch_live_envelope(
    *,
    request_id: str,
    url: str,
    governance: SourceGovernanceSnapshot,
    adapter_id: str,
    adapter_version: str,
    max_bytes: int = MAX_CONTENT_BYTES,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    allowed_url_patterns: Optional[Sequence[str]] = None,
    trust_level: str = "official",
    review_required: bool = True,
    http_get: Optional[HttpGet] = None,
) -> FetchEnvelope:
    """Governance gate → live HTTPS transport → FetchEnvelope (same shape as fixtures)."""
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
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        url=url,
        response=response,
        max_bytes=max_bytes,
        allowed_domain=governance.allowed_domain,
    )
