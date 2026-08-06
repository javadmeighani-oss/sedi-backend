"""I5-IMPL-W3-P02 — source discovery wiring (activation off; no live network).

Selects eligible governed sources, enforces fail-closed governance, resolves
W3-P01 adapters, and builds deduped discovery work items. Persistence of raw
evidence / provenance remains W1-P02; controlled network remains W6-P01.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional, Sequence

from backend.app.schemas.i5_adapters import SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    ADAPTER_MODES,
    AdapterFrameworkError,
    AdapterRegistry,
    assert_safe_public_https_url,
    assert_source_governance_allows_controlled_use,
    default_registry,
)

PACKAGE_ID = "I5-IMPL-W3-P02"
MANAGEMENT_ALIAS = "P07"
PACKAGE_TITLE = (
    "Weekly orchestrator job + discovery wiring (implementation only; activation off)"
)

ELIGIBLE_REGISTRY_STATES = frozenset({"ACTIVE"})
ELIGIBLE_RUNTIME_STATES = frozenset({"ELIGIBLE"})


@dataclass(frozen=True)
class SourceCandidateDescriptor:
    """In-memory discovery input (DB GSP rows map into this; no new ORM)."""

    source_profile_id: int
    adapter_mode: str
    url: str
    registry_state: str
    runtime_eligibility: str
    rights_terms_state: str = "UNKNOWN"
    robots_access_state: str = "UNKNOWN"
    rate_limit_policy: str = "UNKNOWN"
    allowed_domain: Optional[str] = None
    source_version_id: Optional[int] = None
    canonical_key: Optional[str] = None


@dataclass(frozen=True)
class DiscoveryWorkItem:
    work_key: str
    source_profile_id: int
    source_version_id: Optional[int]
    adapter_id: str
    adapter_mode: str
    adapter_version: str
    canonical_url: str
    governance: SourceGovernanceSnapshot


@dataclass
class DiscoveryPlan:
    selected: list[DiscoveryWorkItem] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    blocked: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)

    @property
    def eligible_count(self) -> int:
        return len(self.selected)


def _sha256_text(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def is_structurally_eligible(descriptor: SourceCandidateDescriptor) -> bool:
    return (
        descriptor.registry_state in ELIGIBLE_REGISTRY_STATES
        and descriptor.runtime_eligibility in ELIGIBLE_RUNTIME_STATES
    )


def to_governance_snapshot(descriptor: SourceCandidateDescriptor) -> SourceGovernanceSnapshot:
    return SourceGovernanceSnapshot(
        source_profile_id=descriptor.source_profile_id,
        registry_state=descriptor.registry_state,
        runtime_eligibility=descriptor.runtime_eligibility,
        rights_terms_state=descriptor.rights_terms_state,
        robots_access_state=descriptor.robots_access_state,
        rate_limit_policy=descriptor.rate_limit_policy,
        allowed_domain=descriptor.allowed_domain,
    )


def select_eligible_sources(
    candidates: Sequence[SourceCandidateDescriptor],
) -> tuple[list[SourceCandidateDescriptor], list[dict]]:
    """Filter to ACTIVE+ELIGIBLE; others become skipped records (not selected)."""
    selected: list[SourceCandidateDescriptor] = []
    skipped: list[dict] = []
    for candidate in candidates:
        if is_structurally_eligible(candidate):
            selected.append(candidate)
        else:
            skipped.append(
                {
                    "source_profile_id": candidate.source_profile_id,
                    "reason": "NOT_ELIGIBLE_OR_NOT_ACTIVE",
                    "registry_state": candidate.registry_state,
                    "runtime_eligibility": candidate.runtime_eligibility,
                }
            )
    return selected, skipped


def resolve_adapter_for_mode(
    adapter_mode: str,
    *,
    registry: Optional[AdapterRegistry] = None,
):
    mode = (adapter_mode or "").strip()
    if mode not in ADAPTER_MODES:
        raise AdapterFrameworkError("ADAPTER_UNKNOWN", f"mode:{mode or 'empty'}")
    reg = registry or default_registry()
    return reg.resolve_by_mode(mode)


def build_discovery_work_item(
    descriptor: SourceCandidateDescriptor,
    *,
    registry: Optional[AdapterRegistry] = None,
) -> DiscoveryWorkItem:
    """Governance fail-closed + adapter resolve + URL safety + work-key identity."""
    if descriptor.adapter_mode not in ADAPTER_MODES:
        raise AdapterFrameworkError("ADAPTER_UNKNOWN", descriptor.adapter_mode)
    governance = to_governance_snapshot(descriptor)
    assert_source_governance_allows_controlled_use(governance)
    adapter = resolve_adapter_for_mode(descriptor.adapter_mode, registry=registry)
    meta = adapter.metadata()
    canonical = assert_safe_public_https_url(
        descriptor.url,
        allowed_domain=descriptor.allowed_domain,
    )
    work_key = _sha256_text(
        str(descriptor.source_profile_id),
        str(descriptor.source_version_id or ""),
        meta.adapter_id,
        meta.adapter_version,
        canonical,
    )
    return DiscoveryWorkItem(
        work_key=work_key,
        source_profile_id=descriptor.source_profile_id,
        source_version_id=descriptor.source_version_id,
        adapter_id=meta.adapter_id,
        adapter_mode=meta.mode,
        adapter_version=meta.adapter_version,
        canonical_url=canonical,
        governance=governance,
    )


def dedupe_discovery_items(items: Iterable[DiscoveryWorkItem]) -> list[DiscoveryWorkItem]:
    """Preserve first occurrence of each work_key (source/adapter/url identity)."""
    seen: set[str] = set()
    out: list[DiscoveryWorkItem] = []
    for item in items:
        if item.work_key in seen:
            continue
        seen.add(item.work_key)
        out.append(item)
    return out


def plan_discovery(
    candidates: Sequence[SourceCandidateDescriptor],
    *,
    registry: Optional[AdapterRegistry] = None,
) -> DiscoveryPlan:
    """Full discovery plan: select → govern → resolve → dedupe; record failures."""
    plan = DiscoveryPlan()
    eligible, skipped = select_eligible_sources(candidates)
    plan.skipped.extend(skipped)
    built: list[DiscoveryWorkItem] = []
    for descriptor in eligible:
        try:
            built.append(build_discovery_work_item(descriptor, registry=registry))
        except AdapterFrameworkError as exc:
            bucket = plan.blocked if exc.category.endswith("BLOCKED") or exc.category in {
                "GOVERNANCE_BLOCKED",
                "ROBOTS_BLOCKED",
                "TERMS_BLOCKED",
                "UNSAFE_URL",
            } else plan.failed
            if exc.category in {"ADAPTER_UNKNOWN", "ADAPTER_DISABLED", "DUPLICATE_ADAPTER"}:
                bucket = plan.failed
            if exc.category in {
                "GOVERNANCE_BLOCKED",
                "ROBOTS_BLOCKED",
                "TERMS_BLOCKED",
                "UNSAFE_URL",
            }:
                bucket = plan.blocked
            bucket.append(
                {
                    "source_profile_id": descriptor.source_profile_id,
                    "error_category": exc.category,
                    "detail": str(exc),
                }
            )
    plan.selected = dedupe_discovery_items(built)
    return plan


def map_gsp_row_to_descriptor(
    *,
    source_profile_id: int,
    registry_state: str,
    runtime_eligibility: str,
    adapter_mode: str,
    url: str,
    rights_terms_state: str = "UNKNOWN",
    robots_access_state: str = "UNKNOWN",
    rate_limit_policy: str = "UNKNOWN",
    allowed_domain: Optional[str] = None,
    source_version_id: Optional[int] = None,
    canonical_key: Optional[str] = None,
) -> SourceCandidateDescriptor:
    """Explicit mapper from GSP fields + caller-supplied adapter/url (no invented columns)."""
    return SourceCandidateDescriptor(
        source_profile_id=source_profile_id,
        adapter_mode=adapter_mode,
        url=url,
        registry_state=registry_state,
        runtime_eligibility=runtime_eligibility,
        rights_terms_state=rights_terms_state,
        robots_access_state=robots_access_state,
        rate_limit_policy=rate_limit_policy,
        allowed_domain=allowed_domain,
        source_version_id=source_version_id,
        canonical_key=canonical_key,
    )


def discovery_traceability(item: DiscoveryWorkItem) -> Mapping[str, object]:
    return {
        "work_key": item.work_key,
        "source_profile_id": item.source_profile_id,
        "source_version_id": item.source_version_id,
        "adapter_id": item.adapter_id,
        "adapter_mode": item.adapter_mode,
        "adapter_version": item.adapter_version,
        "canonical_url": item.canonical_url,
    }
