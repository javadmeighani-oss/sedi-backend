"""I5-IMPL-W3-P01 — adapter result / handoff schemas (no persistence models)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

PACKAGE_ID = "I5-IMPL-W3-P01"
MANAGEMENT_ALIAS = "P06"
PACKAGE_TITLE = (
    "Adapter framework + parse/extract/normalize/dedupe (no source activation)"
)


@dataclass(frozen=True)
class AdapterMetadata:
    adapter_id: str
    adapter_version: str
    mode: str
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class SourceGovernanceSnapshot:
    source_profile_id: Optional[int]
    registry_state: str
    runtime_eligibility: str
    rights_terms_state: str
    robots_access_state: str
    rate_limit_policy: str
    allowed_domain: Optional[str] = None


@dataclass(frozen=True)
class FetchEnvelope:
    request_id: str
    adapter_id: str
    adapter_version: str
    canonical_url: str
    http_status: int
    final_url: str
    retrieved_at: datetime
    content_type: str
    charset: str
    byte_count: int
    content_hash: str
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    disposition: str = "OK"
    retryable: bool = False
    error_category: Optional[str] = None
    body: bytes = b""


@dataclass(frozen=True)
class ExtractionCandidate:
    title: str
    normalized_text: str
    language: str
    source_location: str
    content_hash: str
    extractor_version: str
    extraction_confidence: float
    warnings: tuple[str, ...] = ()
    section_anchor: Optional[str] = None
    claim_candidate: Optional[str] = None
    applicability: Optional[str] = None


@dataclass(frozen=True)
class NormalizedDocument:
    domain: str
    topic: str
    population: str
    jurisdiction: str
    normalized_content_canonical: str
    content_hash: str
    dedupe_key: str
    language: str = "en"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterPipelineResult:
    adapter_id: str
    mode: str
    fetch: FetchEnvelope
    normalized: Optional[NormalizedDocument] = None
    candidates: tuple[ExtractionCandidate, ...] = ()
    error_category: Optional[str] = None
    knowledge_unit_approved: bool = False
    source_activated: bool = False
    production_write: bool = False
    live_network_used: bool = False
    diagnostics: dict[str, str] = field(default_factory=dict)
