"""Bounded source-discovery foundation (trusted seeds only; no auto-activation)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence
from urllib.parse import urlparse

from backend.app.services.i5.adapters.base import (
    AdapterFrameworkError,
    assert_safe_public_https_url,
)

DISCOVERY_LIFECYCLE = frozenset(
    {
        "DISCOVERED",
        "IDENTITY_VERIFIED",
        "AUTHORITY_REVIEW",
        "RIGHTS_REVIEW",
        "FORMAT_VERIFIED",
        "APPROVED",
        "ACTIVE",
        "BLOCKED",
        "DEFERRED",
        "SUPERSEDED",
        "REVOKED",
    }
)

_SITEMAP_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_HREF = re.compile(r"""href=["']([^"']+)["']""", re.I)
_FEED_HINTS = ("rss", "atom", "feed", "sitemap", "oai", "api", "openapi", "swagger")


@dataclass(frozen=True)
class EndpointCandidate:
    url: str
    endpoint_kind: str  # api|rss|atom|sitemap|oai|html|unknown
    seed_org_domain: str
    auto_activate: bool = False


@dataclass
class DiscoveryCandidateRecord:
    canonical_url: str
    seed_org_domain: str
    endpoint_kind: str
    lifecycle: str = "DISCOVERED"
    identity_verified: bool = False
    domain_trusted_by_name_alone: bool = False
    auto_activate: bool = False
    notes: List[str] = field(default_factory=list)


def assert_domain_not_trusted_by_name_alone(hostname: str) -> None:
    """Medical-sounding hostnames must not imply trust."""
    host = (hostname or "").lower().strip(".")
    bait = (
        "medline",
        "pubmed",
        "whohealth",
        "clinic",
        "hospital",
        "pharma",
        "nih-",
        "cdc-",
    )
    # Always require explicit seed allowlist / registry — never auto-trust
    if any(b in host for b in bait) or host.endswith(".health") or "medical" in host:
        # Signal: name alone is insufficient (caller must still verify identity)
        return
    return


def _endpoint_kind(url: str) -> str:
    u = url.lower()
    if "sitemap" in u:
        return "sitemap"
    if "oai" in u or "pmh" in u:
        return "oai"
    if "atom" in u:
        return "atom"
    if "rss" in u or "/feed" in u:
        return "rss"
    if "/api" in u or "openapi" in u:
        return "api"
    if u.endswith(".xml"):
        return "xml"
    return "html"


def bounded_discover_endpoints(
    seed_org_domain: str,
    homepage_html_or_sitemap_snippet: str,
    *,
    max_candidates: int = 50,
) -> List[EndpointCandidate]:
    """Parse sitemap/HTML snippet for endpoints under a trusted seed domain.

    No network. Unknown domains recorded with auto_activate=False.
    """
    seed = seed_org_domain.lower().lstrip(".")
    text = homepage_html_or_sitemap_snippet or ""
    found: List[str] = []
    found.extend(_SITEMAP_LOC.findall(text))
    found.extend(_HREF.findall(text))
    # Relative path hints
    for hint in _FEED_HINTS:
        for m in re.finditer(rf"[\"'](/[^\"']*{hint}[^\"']*)[\"']", text, re.I):
            found.append(f"https://{seed}{m.group(1)}")

    out: List[EndpointCandidate] = []
    seen = set()
    for raw in found:
        if len(out) >= max_candidates:
            break
        url = raw.strip()
        if not url or url in seen:
            continue
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("/"):
            url = f"https://{seed}{url}"
        try:
            normalized = assert_safe_public_https_url(url, allowed_domain=None)
        except AdapterFrameworkError:
            continue
        host = (urlparse(normalized).hostname or "").lower()
        assert_domain_not_trusted_by_name_alone(host)
        under_seed = host == seed or host.endswith("." + seed)
        kind = _endpoint_kind(normalized)
        seen.add(url)
        out.append(
            EndpointCandidate(
                url=normalized,
                endpoint_kind=kind,
                seed_org_domain=seed,
                auto_activate=False if not under_seed else False,  # never auto-activate
            )
        )
    return out


def classify_candidate(
    endpoint: EndpointCandidate,
    *,
    identity_verified: bool = False,
    lifecycle: str = "DISCOVERED",
) -> DiscoveryCandidateRecord:
    if lifecycle not in DISCOVERY_LIFECYCLE:
        raise ValueError(f"INVALID_LIFECYCLE:{lifecycle}")
    # Never escalate to ACTIVE/APPROVED here — discovery is queue-only
    if lifecycle in {"ACTIVE", "APPROVED"}:
        lifecycle = "RIGHTS_REVIEW"
    notes = ["REGISTRY_ENTRY!=AUTOMATION_APPROVED", "NO_AUTO_ACTIVATE"]
    if not identity_verified:
        notes.append("IDENTITY_UNVERIFIED")
    host = (urlparse(endpoint.url).hostname or "").lower()
    under_seed = host == endpoint.seed_org_domain or host.endswith("." + endpoint.seed_org_domain)
    if not under_seed:
        notes.append("OFF_SEED_DOMAIN_CANDIDATE_ONLY")
        lifecycle = "DISCOVERED"
    return DiscoveryCandidateRecord(
        canonical_url=endpoint.url,
        seed_org_domain=endpoint.seed_org_domain,
        endpoint_kind=endpoint.endpoint_kind,
        lifecycle=lifecycle,
        identity_verified=identity_verified,
        domain_trusted_by_name_alone=False,
        auto_activate=False,
        notes=notes,
    )


def queue_for_rights_review(candidates: Sequence[DiscoveryCandidateRecord]) -> List[DiscoveryCandidateRecord]:
    queued: List[DiscoveryCandidateRecord] = []
    for c in candidates:
        queued.append(
            DiscoveryCandidateRecord(
                canonical_url=c.canonical_url,
                seed_org_domain=c.seed_org_domain,
                endpoint_kind=c.endpoint_kind,
                lifecycle="RIGHTS_REVIEW",
                identity_verified=c.identity_verified,
                domain_trusted_by_name_alone=False,
                auto_activate=False,
                notes=list(c.notes) + ["QUEUED_RIGHTS_REVIEW"],
            )
        )
    return queued
