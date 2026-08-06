"""I5-IMPL-W3-P01 — adapter base protocol, registry, governance + URL safety gates.

No live network. Concrete adapters consume fixture bytes / envelopes only.
KnowledgeSourceFetcher is referenced as PUBLIC_WEB substrate (READ_ONLY wrap).
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, MutableMapping, Optional, Sequence
from urllib.parse import urlparse

from backend.app.schemas.i5_adapters import (
    AdapterMetadata,
    FetchEnvelope,
    SourceGovernanceSnapshot,
)
from backend.app.services.gate3 import knowledge_source_fetcher as _ksf

# Frozen API_OR_FEED_MODE literals (target_architecture_map / §172.17).
ADAPTER_MODES: frozenset[str] = frozenset(
    {
        "OFFICIAL_API",
        "OFFICIAL_XML",
        "OFFICIAL_JSON",
        "RSS_OR_FEED",
        "PUBLIC_WEB_FETCH",
        "MANUAL_OR_LINK_ONLY",
        "BLOCKED_OR_EXCLUDED",
    }
)

ADAPTER_CAPABILITIES: frozenset[str] = frozenset(
    {
        "DISCOVERY",
        "FETCH",
        "PAGINATION",
        "CONDITIONAL_FETCH",
        "EXTRACTION",
        "ATTACHMENT_HANDLING",
        "LANGUAGE_SUPPORT",
        "CONTENT_TYPES",
    }
)

ERROR_CATEGORIES: frozenset[str] = frozenset(
    {
        "GOVERNANCE_BLOCKED",
        "ROBOTS_BLOCKED",
        "TERMS_BLOCKED",
        "RATE_LIMITED",
        "TIMEOUT",
        "NETWORK_ERROR",
        "NOT_FOUND",
        "GONE",
        "INVALID_CONTENT_TYPE",
        "CONTENT_TOO_LARGE",
        "PARSING_FAILED",
        "EXTRACTION_FAILED",
        "UNSUPPORTED_FORMAT",
        "PROVENANCE_INCOMPLETE",
        "NO_MATERIAL_CHANGE",
        "UNSAFE_URL",
        "ADAPTER_UNKNOWN",
        "ADAPTER_DISABLED",
        "DUPLICATE_ADAPTER",
    }
)

_ACCEPTABLE_RIGHTS = frozenset({"ACCEPTABLE", "APPROVED", "OGL", "PUBLIC_DOMAIN"})
_ACCEPTABLE_ROBOTS = frozenset({"ALLOWED", "ACCEPTABLE", "APPROVED"})
_ACCEPTABLE_RATE = frozenset({"DEFINED", "ACCEPTABLE", "APPROVED"})
_BLOCKING_REGISTRY = frozenset({"BLOCKED", "REVOKED", "ARCHIVED"})
_BLOCKING_ELIGIBILITY = frozenset({"NOT_ELIGIBLE", "REVOKED", "SUSPENDED"})

MAX_CONTENT_BYTES = 2_097_152
DEFAULT_TIMEOUT_SECONDS = 15
ALLOWED_SCHEMES = frozenset({"https"})
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "169.254.169.254",
    }
)


class AdapterFrameworkError(ValueError):
    """Fail-closed adapter framework error."""

    def __init__(self, category: str, detail: str = "") -> None:
        if category not in ERROR_CATEGORIES:
            raise ValueError(f"UNKNOWN_ERROR_CATEGORY:{category}")
        self.category = category
        message = category if not detail else f"{category}:{detail}"
        super().__init__(message)


@dataclass(frozen=True)
class FixtureTransportResponse:
    """Deterministic transport substitute — never performs network I/O."""

    status_code: int
    body: bytes
    content_type: str = "text/html; charset=utf-8"
    final_url: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    headers: Mapping[str, str] | None = None


FixtureTransport = Callable[[str], FixtureTransportResponse]


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        raise AdapterFrameworkError("UNSAFE_URL", "empty")
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise AdapterFrameworkError("UNSAFE_URL", "scheme")
    if not parsed.hostname:
        raise AdapterFrameworkError("UNSAFE_URL", "hostname")
    host = parsed.hostname.lower()
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    return f"https://{host}{path}{query}"


def assert_safe_public_https_url(url: str, *, allowed_domain: Optional[str] = None) -> str:
    """Pure URL SSRF policy (no DNS). HTTPS-only; blocks private/loopback literals."""
    normalized = canonical_url(url)
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        raise AdapterFrameworkError("UNSAFE_URL", "blocked_host")
    if host.startswith("127.") or host == "::1":
        raise AdapterFrameworkError("UNSAFE_URL", "loopback")
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            raise AdapterFrameworkError("UNSAFE_URL", "private_ip")
    except ValueError:
        pass
    if allowed_domain:
        allowed = allowed_domain.lower().lstrip(".")
        if not (host == allowed or host.endswith("." + allowed)):
            raise AdapterFrameworkError("UNSAFE_URL", "domain_not_allowed")
    if parsed.scheme.lower() in {"file", "ftp", "http"}:
        raise AdapterFrameworkError("UNSAFE_URL", "scheme")
    return normalized


def assert_source_governance_allows_controlled_use(
    snapshot: SourceGovernanceSnapshot,
) -> None:
    """Fail-closed structural governance gate (no activation)."""
    if snapshot.registry_state in _BLOCKING_REGISTRY:
        raise AdapterFrameworkError("GOVERNANCE_BLOCKED", "registry")
    if snapshot.runtime_eligibility in _BLOCKING_ELIGIBILITY:
        raise AdapterFrameworkError("GOVERNANCE_BLOCKED", "eligibility")
    rights = (snapshot.rights_terms_state or "UNKNOWN").upper()
    robots = (snapshot.robots_access_state or "UNKNOWN").upper()
    rate = (snapshot.rate_limit_policy or "UNKNOWN").upper()
    if rights not in _ACCEPTABLE_RIGHTS:
        if rights in {"REJECTED", "BLOCKED"}:
            raise AdapterFrameworkError("TERMS_BLOCKED", "rights")
        raise AdapterFrameworkError("GOVERNANCE_BLOCKED", "rights")
    if robots not in _ACCEPTABLE_ROBOTS:
        if robots in {"BLOCKED", "DISALLOWED", "DENIED"}:
            raise AdapterFrameworkError("ROBOTS_BLOCKED", "robots")
        raise AdapterFrameworkError("GOVERNANCE_BLOCKED", "robots")
    if rate not in _ACCEPTABLE_RATE:
        raise AdapterFrameworkError("GOVERNANCE_BLOCKED", "rate_limit")


def map_http_status_to_category(status: int) -> Optional[str]:
    if status == 200:
        return None
    if status == 304:
        return "NO_MATERIAL_CHANGE"
    if status == 404:
        return "NOT_FOUND"
    if status == 410:
        return "GONE"
    if status == 429:
        return "RATE_LIMITED"
    if status >= 500:
        return "NETWORK_ERROR"
    if status in {408, 504}:
        return "TIMEOUT"
    return "NETWORK_ERROR"


def build_fetch_envelope(
    *,
    request_id: str,
    adapter_id: str,
    adapter_version: str,
    url: str,
    response: FixtureTransportResponse,
    max_bytes: int = MAX_CONTENT_BYTES,
    allowed_domain: Optional[str] = None,
) -> FetchEnvelope:
    safe_url = assert_safe_public_https_url(url, allowed_domain=allowed_domain)
    final = response.final_url or safe_url
    assert_safe_public_https_url(final, allowed_domain=allowed_domain)
    body = response.body or b""
    if len(body) > max_bytes:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", str(len(body)))
    category = map_http_status_to_category(int(response.status_code))
    disposition = "OK" if category is None else category
    charset = "utf-8"
    ctype = response.content_type or "application/octet-stream"
    m = re.search(r"charset=([\w-]+)", ctype, flags=re.I)
    if m:
        charset = m.group(1).lower()
    return FetchEnvelope(
        request_id=request_id,
        adapter_id=adapter_id,
        adapter_version=adapter_version,
        canonical_url=safe_url,
        http_status=int(response.status_code),
        final_url=canonical_url(final),
        retrieved_at=utc_now(),
        content_type=ctype.split(";", 1)[0].strip().lower(),
        charset=charset,
        byte_count=len(body),
        content_hash=sha256_hex(body),
        etag=response.etag,
        last_modified=response.last_modified,
        disposition=disposition,
        retryable=category in {"NETWORK_ERROR", "TIMEOUT", "RATE_LIMITED"},
        error_category=category,
        body=body if category is None else b"",
    )


class SourceAdapter(ABC):
    """Adapter protocol — stages are separate for audit boundaries."""

    @abstractmethod
    def metadata(self) -> AdapterMetadata:
        raise NotImplementedError

    @abstractmethod
    def fetch_fixture(
        self,
        *,
        request_id: str,
        url: str,
        transport: FixtureTransport,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
    ) -> FetchEnvelope:
        raise NotImplementedError


class AdapterRegistry:
    """In-process adapter-type registry (not ISR source-profile registry)."""

    def __init__(self) -> None:
        self._by_id: MutableMapping[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        meta = adapter.metadata()
        if meta.mode not in ADAPTER_MODES:
            raise AdapterFrameworkError("UNSUPPORTED_FORMAT", meta.mode)
        if meta.adapter_id in self._by_id:
            raise AdapterFrameworkError("DUPLICATE_ADAPTER", meta.adapter_id)
        unknown_caps = set(meta.capabilities) - ADAPTER_CAPABILITIES
        if unknown_caps:
            raise AdapterFrameworkError("UNSUPPORTED_FORMAT", ",".join(sorted(unknown_caps)))
        self._by_id[meta.adapter_id] = adapter

    def get(self, adapter_id: str) -> SourceAdapter:
        adapter = self._by_id.get(adapter_id)
        if adapter is None:
            raise AdapterFrameworkError("ADAPTER_UNKNOWN", adapter_id)
        return adapter

    def resolve_by_mode(self, mode: str) -> SourceAdapter:
        if mode not in ADAPTER_MODES:
            raise AdapterFrameworkError("UNSUPPORTED_FORMAT", mode)
        if mode == "BLOCKED_OR_EXCLUDED":
            raise AdapterFrameworkError("ADAPTER_DISABLED", mode)
        if mode == "MANUAL_OR_LINK_ONLY":
            raise AdapterFrameworkError("ADAPTER_DISABLED", mode)
        for adapter in self._by_id.values():
            if adapter.metadata().mode == mode:
                return adapter
        raise AdapterFrameworkError("ADAPTER_UNKNOWN", mode)

    def list_ids(self) -> Sequence[str]:
        return tuple(sorted(self._by_id))


def public_web_fetcher_substrate_symbol() -> str:
    """Prove READ_ONLY wrap of Gate3 KnowledgeSourceFetcher (no live call)."""
    return f"{_ksf.KnowledgeSourceFetcher.__module__}.{_ksf.KnowledgeSourceFetcher.__name__}"


def default_registry() -> AdapterRegistry:
    from backend.app.services.i5.adapters.official_api import OfficialApiAdapter
    from backend.app.services.i5.adapters.public_web_fetch import PublicWebFetchAdapter
    from backend.app.services.i5.adapters.rss_feed import RssFeedAdapter

    registry = AdapterRegistry()
    registry.register(PublicWebFetchAdapter())
    registry.register(OfficialApiAdapter())
    registry.register(RssFeedAdapter())
    return registry
