"""Autonomous governed source discovery + qualification + monitoring (no activation).

DISCOVERY != AUTHORIZATION
CANDIDATE != QUALIFIED
QUALIFIED != ACTIVE
AUTO_ACTIVATION = NO
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from urllib import robotparser
from urllib.parse import urlparse

import yaml

from backend.app.services.i5.adapters.format_drift import classify_format_drift
from backend.app.services.i5.candidate_qualification_registry import (
    ALLOWED_STATUSES,
    REGISTRY_RELATIVE,
    candidate_rows,
    load_candidate_qualification_registry,
)
from backend.app.services.i5.trusted_source_manifest import (
    active_manifest_rows,
    load_trusted_source_manifest,
)

SEED_CATALOG_RELATIVE = Path("backend/config/i5/autonomous_discovery_seed_catalog_v1.yaml")
COVERAGE_MANIFEST_RELATIVE = Path("backend/config/i5/coverage_manifest_v1.yaml")
WAVE02_GAPS_RELATIVE = Path("backend/config/i5/wave02_candidate_source_gaps_v1.yaml")

MONITOR_CHANGE_KINDS = frozenset(
    {
        "CONTENT_CHANGE",
        "FORMAT_CHANGE",
        "ACCESS_CHANGE",
        "RIGHTS_CHANGE",
        "ROBOTS_CHANGE",
        "SOURCE_IDENTITY_CHANGE",
        "NO_MATERIAL_CHANGE",
        "STALE_SIGNAL",
        "SOURCE_DISAPPEARED",
    }
)

# Hard-blocked activation keys for this Gate (even if QUALIFIED).
ACTIVATION_HARD_BLOCK = frozenset(
    {
        "owh_womens_health",
        "cdc_child_development",
        "cdc_ncezid_infectious",
    }
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "backend" / "config" / "i5").is_dir():
            return parent
    return Path.cwd()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_domain(value: str) -> str:
    host = (value or "").strip().lower()
    host = re.sub(r"^https?://", "", host)
    host = host.split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_url_family(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    parsed = urlparse(u if "://" in u else f"https://{u}")
    host = normalize_domain(parsed.netloc or parsed.path)
    path = parsed.path.rstrip("/") or ""
    return f"https://{host}{path}".lower()


def candidate_identity_key(
    *,
    publisher: str = "",
    canonical_domain: str = "",
    candidate_url_family: str = "",
    candidate_id: str = "",
) -> str:
    """Stable dedupe key across domain aliases and trailing-slash URL variants."""
    domain = normalize_domain(canonical_domain) or normalize_domain(
        urlparse(candidate_url_family if "://" in (candidate_url_family or "") else f"https://{candidate_url_family or ''}").netloc
    )
    family = normalize_url_family(candidate_url_family)
    # Prefer domain+path family; fall back to candidate_id.
    if domain and family:
        return f"{domain}|{family}"
    if candidate_id:
        return f"id|{candidate_id.strip().lower()}"
    return f"pub|{(publisher or '').strip().lower()}|{domain}"


@lru_cache(maxsize=1)
def load_seed_catalog() -> dict[str, Any]:
    path = _repo_root() / SEED_CATALOG_RELATIVE
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if data.get("activation_policy") != "DISCOVERY_ONLY_NO_ACTIVATION":
        raise ValueError("BAD_SEED_CATALOG_POLICY")
    return data


@lru_cache(maxsize=1)
def load_coverage_manifest() -> dict[str, Any]:
    path = _repo_root() / COVERAGE_MANIFEST_RELATIVE
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def load_wave02_gaps() -> dict[str, Any]:
    path = _repo_root() / WAVE02_GAPS_RELATIVE
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@dataclass
class MonitorFinding:
    subject_id: str
    subject_kind: str  # ACTIVE_SOURCE | QUALIFIED_CANDIDATE
    change_kind: str
    detail: str
    fail_closed: bool = False
    observed_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if d["change_kind"] not in MONITOR_CHANGE_KINDS:
            raise ValueError(f"BAD_CHANGE_KIND:{d['change_kind']}")
        return d


def _ensure_history(row: dict[str, Any]) -> None:
    if "history" not in row or row["history"] is None:
        row["history"] = []
    if not row.get("first_seen"):
        row["first_seen"] = utc_now_iso()
    row["last_seen"] = utc_now_iso()
    # Activation must never flip from discovery/qualification.
    row["activation"] = "NO"


def seed_to_candidate(seed: dict[str, Any], *, discovered_at: Optional[str] = None) -> dict[str, Any]:
    ts = discovered_at or utc_now_iso()
    cid = str(seed.get("candidate_id") or "").strip()
    row = {
        "candidate_id": cid,
        "publisher": seed.get("publisher"),
        "canonical_domain": normalize_domain(str(seed.get("canonical_domain") or "")),
        "candidate_url_family": normalize_url_family(str(seed.get("candidate_url_family") or seed.get("url_family") or "")),
        "url_family": normalize_url_family(str(seed.get("candidate_url_family") or seed.get("url_family") or "")),
        "target_dxx_kd": seed.get("target_dxx_kd") or seed.get("dxx"),
        "authority_class": seed.get("authority_class"),
        "discovery_reason": seed.get("discovery_reason") or seed.get("why_needed") or "GOVERNED_DISCOVERY",
        "discovered_at": ts,
        "discovery_method": seed.get("discovery_method") or "GOVERNED_SEED_CATALOG",
        "rights_state": seed.get("rights_state") or "UNKNOWN",
        "robots_state": seed.get("robots_state") or "UNKNOWN",
        "access_state": seed.get("access_state") or "UNKNOWN",
        "format": seed.get("format") or "HTML_PUBLIC_WEB",
        "freshness_signal": seed.get("freshness_signal") or seed.get("freshness") or "UNKNOWN",
        "qualification_status": "DISCOVERED",
        "qualification_reason": "CANDIDATE_ONLY_NEEDS_QUALIFICATION",
        "activation": "NO",
        "activation_authorized_this_gate": "NO",
        "first_seen": ts,
        "last_seen": ts,
        "history": [
            {
                "at": ts,
                "from_status": None,
                "to_status": "DISCOVERED",
                "reason": "autonomous_discovery",
            }
        ],
    }
    return row


def discover_candidates(*, include_wave02_gaps: bool = True) -> list[dict[str, Any]]:
    """Bounded autonomous discovery from seed catalog (+ optional gap list). Never ACTIVE."""
    out: list[dict[str, Any]] = []
    for seed in load_seed_catalog().get("seeds") or []:
        out.append(seed_to_candidate(seed))
    if include_wave02_gaps:
        for gap in load_wave02_gaps().get("candidates") or []:
            # Only promote gaps that are still CANDIDATE_ONLY and not already in registry by id.
            cid = str(gap.get("candidate_publisher") or "").strip().lower().replace(" ", "_")
            synthetic = {
                "candidate_id": f"gap_{gap.get('dxx', 'xx').lower()}_{cid}"[:64],
                "publisher": gap.get("candidate_publisher"),
                "canonical_domain": normalize_domain(
                    urlparse(str(gap.get("candidate_url_or_family") or "")).netloc
                ),
                "candidate_url_family": gap.get("candidate_url_or_family"),
                "target_dxx_kd": gap.get("dxx"),
                "authority_class": gap.get("authority_class"),
                "discovery_reason": f"WAVE02_GAP:{gap.get('why_needed')}",
                "discovery_method": "WAVE02_CANDIDATE_SOURCE_GAPS",
                "rights_state": gap.get("rights_state"),
                "robots_state": gap.get("robots_state"),
                "access_state": "UNKNOWN",
                "format": "HTML_PUBLIC_WEB",
                "freshness_signal": "GAP_LIST",
            }
            out.append(seed_to_candidate(synthetic))
    # Enforce never-active
    for row in out:
        row["activation"] = "NO"
        if row.get("qualification_status") not in ALLOWED_STATUSES:
            row["qualification_status"] = "DISCOVERED"
    return out


def _index_by_identity(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = candidate_identity_key(
            publisher=str(row.get("publisher") or ""),
            canonical_domain=str(row.get("canonical_domain") or ""),
            candidate_url_family=str(row.get("candidate_url_family") or row.get("url_family") or ""),
            candidate_id=str(row.get("candidate_id") or ""),
        )
        # Prefer first-seen / keep existing over alias probes
        if key not in idx:
            idx[key] = row
        else:
            # Update last_seen on duplicate
            existing = idx[key]
            _ensure_history(existing)
            existing["last_seen"] = utc_now_iso()
            existing.setdefault("alias_hits", 0)
            existing["alias_hits"] = int(existing.get("alias_hits") or 0) + 1
    return idx


def merge_discovered_into_registry(
    discovered: list[dict[str, Any]],
    *,
    base_rows: Optional[list[dict[str, Any]]] = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Dedupe publisher/domain/url-family; preserve history; never delete rejected."""
    base = deepcopy(base_rows if base_rows is not None else candidate_rows())
    for row in base:
        _ensure_history(row)
        # Normalize fields
        if "candidate_url_family" not in row and row.get("url_family"):
            row["candidate_url_family"] = row["url_family"]
        row["canonical_domain"] = normalize_domain(str(row.get("canonical_domain") or ""))
        row["candidate_url_family"] = normalize_url_family(
            str(row.get("candidate_url_family") or row.get("url_family") or "")
        )
        row["activation"] = "NO"

    by_id = {str(r.get("candidate_id")): r for r in base}
    by_identity = _index_by_identity(base)

    new_count = 0
    dup_suppressed = 0
    for disc in discovered:
        _ensure_history(disc)
        cid = str(disc.get("candidate_id") or "")
        key = candidate_identity_key(
            publisher=str(disc.get("publisher") or ""),
            canonical_domain=str(disc.get("canonical_domain") or ""),
            candidate_url_family=str(disc.get("candidate_url_family") or ""),
            candidate_id=cid,
        )
        if key in by_identity:
            existing = by_identity[key]
            _ensure_history(existing)
            existing["last_seen"] = utc_now_iso()
            existing.setdefault("alias_hits", 0)
            existing["alias_hits"] = int(existing.get("alias_hits") or 0) + 1
            dup_suppressed += 1
            continue
        if cid and cid in by_id:
            existing = by_id[cid]
            _ensure_history(existing)
            existing["last_seen"] = utc_now_iso()
            dup_suppressed += 1
            continue
        # New candidate
        base.append(disc)
        by_id[cid] = disc
        by_identity[key] = disc
        new_count += 1

    return base, {"new_candidates": new_count, "duplicate_suppressed": dup_suppressed}


def _live_http_probe(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    """Bounded live probe. Fail-closed on ambiguity."""
    import urllib.error
    import urllib.request

    result: dict[str, Any] = {
        "url": url,
        "http_status": None,
        "final_url": None,
        "content_type": None,
        "robots_allowed": None,
        "error": None,
        "domain_contained": True,
    }
    try:
        parsed = urlparse(url)
        origin_host = normalize_domain(parsed.netloc)
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SediI5GovernedProbe/1.0; +https://sedi-ai.com)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — governed allowlisted URLs only
            result["http_status"] = getattr(resp, "status", None) or resp.getcode()
            result["final_url"] = resp.geturl()
            result["content_type"] = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            final_host = normalize_domain(urlparse(result["final_url"]).netloc)
            # Containment: final host must be same registrant suffix or exact
            result["domain_contained"] = final_host == origin_host or final_host.endswith("." + origin_host) or origin_host.endswith("." + final_host)
            body_prefix = resp.read(2048)
            result["body_sha16"] = hashlib.sha256(body_prefix).hexdigest()[:16]
    except Exception as exc:  # noqa: BLE001 — probe must never raise into activation
        result["error"] = f"{type(exc).__name__}:{exc}"
        result["http_status"] = None

    # robots.txt
    try:
        robots_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}/robots.txt"
        rp = robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        result["robots_allowed"] = bool(rp.can_fetch("SediI5GovernedProbe/1.0", url))
    except Exception:  # noqa: BLE001
        result["robots_allowed"] = None  # ambiguous → fail-closed at qualify

    return result


def qualify_candidate(
    row: dict[str, Any],
    *,
    live: bool = False,
    active_publisher_domains: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Automated qualification → QUALIFIED | REJECTED | NEEDS_REVIEW. Never activates."""
    out = deepcopy(row)
    _ensure_history(out)
    prev = str(out.get("qualification_status") or "DISCOVERED").upper()
    reasons: list[str] = []
    cid = str(out.get("candidate_id") or "")

    domain = normalize_domain(str(out.get("canonical_domain") or ""))
    url = str(out.get("candidate_url_family") or out.get("url_family") or "")
    authority = str(out.get("authority_class") or "").upper()

    # Publisher / authority
    if not domain or not url:
        out["qualification_status"] = "REJECTED"
        reasons.append("missing_domain_or_url_family")
    elif "OFFICIAL" not in authority and "INTERNATIONAL" not in authority:
        out["qualification_status"] = "NEEDS_REVIEW"
        reasons.append("authority_class_not_official")
    else:
        out["qualification_status"] = "QUALIFIED"
        reasons.append("authority_identity_ok")

    # Overlap with active sources → still QUALIFIED possible but note redundancy
    active_domains = active_publisher_domains or {
        normalize_domain(str(r.get("publisher_family") or "")) for r in active_manifest_rows()
    }
    if domain and any(domain == a or domain.endswith("." + a) or a.endswith("." + domain) for a in active_domains if a):
        reasons.append("overlap_active_publisher_family")

    # WHO / international rights always need human review (even offline).
    if domain == "who.int" or domain.endswith(".who.int") or "WHO" in str(out.get("publisher") or "").upper():
        out["qualification_status"] = "NEEDS_REVIEW"
        out["rights_state"] = "NEEDS_REVIEW"
        reasons.append("who_or_international_rights_needs_review")

    # CDC program paths require dedicated source profiles (never silent lifestyle broaden).
    # Qualification may still PASS; activation remains allowlist-only.
    if cid in {"cdc_child_development", "cdc_ncezid_infectious"} or (
        domain == "cdc.gov"
        and "/niosh/" not in url.lower()
        and cid.startswith("cdc_")
        and cid != "cdc_health_lifestyle"
    ):
        reasons.append("cdc_requires_dedicated_source_profile_not_lifestyle_broaden")

    if cid == "owh_womens_health" or domain in {"womenshealth.gov", "owh.womenshealth.gov"}:
        reasons.append("owh_activation_requires_explicit_allowlist_gate")

    if live and url and out["qualification_status"] != "REJECTED":
        probe = _live_http_probe(url)
        out["live_probe"] = {
            "http_status": probe.get("http_status"),
            "robots_allowed": probe.get("robots_allowed"),
            "domain_contained": probe.get("domain_contained"),
            "content_type": probe.get("content_type"),
            "error": probe.get("error"),
        }
        if probe.get("http_status") is None or probe.get("error"):
            out["qualification_status"] = "NEEDS_REVIEW"
            reasons.append(f"access_ambiguous:{probe.get('error')}")
        elif int(probe["http_status"]) >= 400:
            out["qualification_status"] = "NEEDS_REVIEW"
            reasons.append(f"http_{probe['http_status']}")
        if probe.get("robots_allowed") is None:
            out["qualification_status"] = "NEEDS_REVIEW"
            reasons.append("robots_ambiguous_fail_closed")
            out["robots_state"] = "AMBIGUOUS"
        elif probe.get("robots_allowed") is False:
            out["qualification_status"] = "REJECTED"
            reasons.append("robots_disallow")
            out["robots_state"] = "DISALLOWED"
        else:
            out["robots_state"] = "ALLOWED"
            reasons.append("robots_allowed")
        if probe.get("domain_contained") is False:
            out["qualification_status"] = "REJECTED"
            reasons.append("redirect_domain_escape")
        ct = (probe.get("content_type") or "")
        if ct and "html" not in ct and "xml" not in ct and "json" not in ct and "text" not in ct:
            out["qualification_status"] = "NEEDS_REVIEW"
            reasons.append(f"format_unexpected:{ct}")
        if probe.get("http_status") and int(probe["http_status"]) < 400:
            out["access_state"] = "ALLOWED"
        # Rights: US .gov / nih / who remain candidate-level; never invent license
        if domain.endswith(".gov") or domain.endswith(".nih.gov") or domain == "who.int" or domain.endswith(".who.int"):
            if str(out.get("rights_state") or "").upper() in {"UNKNOWN", "NEEDS_REVIEW"}:
                out["rights_state"] = "PUBLIC_DOMAIN_CANDIDATE" if domain != "who.int" else "NEEDS_REVIEW"
                if domain == "who.int" or domain.endswith(".who.int"):
                    out["qualification_status"] = "NEEDS_REVIEW"
                    reasons.append("who_rights_needs_review")

    # Hard rule: candidate registry never activates (allowlist is sole activation authority).
    out["activation"] = "NO"
    if cid in ACTIVATION_HARD_BLOCK:
        # Historical hard-block IDs remain activation=NO here; Gate-explicit allowlist may still activate.
        out["activation_authorized_this_gate"] = "NO"
        reasons.append("registry_activation_forbidden_use_allowlist")

    # After live PASS, do not keep WHO robots-disallow as QUALIFIED.
    if domain == "who.int" or domain.endswith(".who.int"):
        if str(out.get("robots_state") or "").upper() == "DISALLOWED":
            out["qualification_status"] = "REJECTED"
            reasons.append("who_robots_disallow")
        else:
            out["qualification_status"] = "NEEDS_REVIEW"

    new_status = str(out["qualification_status"]).upper()
    if new_status not in ALLOWED_STATUSES:
        new_status = "NEEDS_REVIEW"
        out["qualification_status"] = new_status
    if new_status != prev:
        out.setdefault("history", []).append(
            {
                "at": utc_now_iso(),
                "from_status": prev,
                "to_status": new_status,
                "reason": ";".join(reasons)[:500],
            }
        )
    out["qualification_reason"] = ";".join(reasons)[:800]
    out["last_seen"] = utc_now_iso()
    return out


def qualify_registry_rows(
    rows: list[dict[str, Any]],
    *,
    live: bool = False,
    only_statuses: Optional[set[str]] = None,
) -> list[dict[str, Any]]:
    only = only_statuses or {"DISCOVERED", "NEEDS_REVIEW"}
    active_domains = {
        normalize_domain(str(r.get("publisher_family") or "")) for r in active_manifest_rows()
    }
    out: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("qualification_status") or "").upper()
        if status in only or (
            str(row.get("candidate_id") or "") in ACTIVATION_HARD_BLOCK
        ):
            out.append(qualify_candidate(row, live=live, active_publisher_domains=active_domains))
        else:
            r = deepcopy(row)
            r["activation"] = "NO"
            out.append(r)
    return out


def monitor_subject(
    *,
    subject_id: str,
    subject_kind: str,
    url: str,
    previous_content_type: Optional[str] = None,
    previous_body_sha16: Optional[str] = None,
    previous_robots_allowed: Optional[bool] = None,
    live: bool = True,
) -> list[MonitorFinding]:
    findings: list[MonitorFinding] = []
    if not live:
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="NO_MATERIAL_CHANGE",
                detail="offline_monitor_stub",
            )
        )
        return findings

    probe = _live_http_probe(url)
    if probe.get("http_status") is None:
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="ACCESS_CHANGE",
                detail=str(probe.get("error") or "unreachable"),
                fail_closed=True,
            )
        )
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="SOURCE_DISAPPEARED",
                detail="http_probe_failed",
                fail_closed=True,
            )
        )
        return findings

    if probe.get("domain_contained") is False:
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="SOURCE_IDENTITY_CHANGE",
                detail=f"redirect_escape:{probe.get('final_url')}",
                fail_closed=True,
            )
        )

    if probe.get("robots_allowed") is None:
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="ROBOTS_CHANGE",
                detail="robots_ambiguous_fail_closed",
                fail_closed=True,
            )
        )
    elif previous_robots_allowed is not None and bool(probe["robots_allowed"]) != bool(previous_robots_allowed):
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="ROBOTS_CHANGE",
                detail=f"robots:{previous_robots_allowed}->{probe['robots_allowed']}",
                fail_closed=not bool(probe["robots_allowed"]),
            )
        )

    cur_ct = (probe.get("content_type") or "unknown").split("/")[-1].upper()
    if "html" in (probe.get("content_type") or ""):
        cur_rep = "HTML"
    elif "json" in (probe.get("content_type") or ""):
        cur_rep = "JSON"
    elif "xml" in (probe.get("content_type") or "") or "rss" in (probe.get("content_type") or ""):
        cur_rep = "RSS_ATOM"
    else:
        cur_rep = "UNKNOWN"
    drift = classify_format_drift(
        source_identity_key=subject_id,
        previous_representation=previous_content_type,
        current_representation=cur_rep,
    )
    if drift.classification != "SAME_SUPPORTED_FORMAT" and previous_content_type:
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="FORMAT_CHANGE",
                detail=drift.classification,
                fail_closed=drift.fail_closed,
            )
        )

    sha = probe.get("body_sha16")
    if previous_body_sha16 and sha and sha != previous_body_sha16:
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="CONTENT_CHANGE",
                detail=f"body_prefix_sha16:{previous_body_sha16}->{sha}",
            )
        )

    if not findings:
        findings.append(
            MonitorFinding(
                subject_id=subject_id,
                subject_kind=subject_kind,
                change_kind="NO_MATERIAL_CHANGE",
                detail=f"http={probe.get('http_status')};ct={cur_ct}",
            )
        )
    return findings


def monitor_active_and_qualified(
    rows: list[dict[str, Any]],
    *,
    live: bool = False,
    max_subjects: int = 16,
) -> list[dict[str, Any]]:
    """Monitor ACTIVE allowlist sources + QUALIFIED candidates. No auto deactivate/activate."""
    load_trusted_source_manifest.cache_clear()
    findings: list[dict[str, Any]] = []
    subjects: list[tuple[str, str, str]] = []
    for r in active_manifest_rows():
        key = str(r.get("source_key") or "")
        urls = list(r.get("exact_urls") or r.get("url_allowlist") or [])
        if not urls:
            continue
        subjects.append((key, "ACTIVE_SOURCE", str(urls[0])))
    for row in rows:
        if str(row.get("qualification_status") or "").upper() != "QUALIFIED":
            continue
        url = str(row.get("candidate_url_family") or row.get("url_family") or "")
        if url:
            subjects.append((str(row.get("candidate_id")), "QUALIFIED_CANDIDATE", url))
    for subject_id, kind, url in subjects[:max_subjects]:
        for f in monitor_subject(subject_id=subject_id, subject_kind=kind, url=url, live=live):
            findings.append(f.to_dict())
    return findings


def depth_class(*, eligible: int, kce: int, active_publishers: int) -> str:
    if eligible <= 0 and kce <= 0:
        return "UNCOVERED" if active_publishers <= 0 else "THIN"
    if eligible >= 3 and kce >= 6 and active_publishers >= 1:
        return "STRONG"
    if eligible >= 1 and kce >= 2:
        return "MODERATE"
    return "THIN"


def build_d01_d19_matrix(
    *,
    per_dxx: Optional[dict[str, dict[str, int]]] = None,
    serving_proof: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    """Compact D01–D19 coverage matrix. Does not invent I5 %."""
    manifest = load_coverage_manifest()
    entities = {e["id"]: e for e in (manifest.get("entities") or [])}
    mapping = manifest.get("source_mapping") or {}
    active_keys = {str(r.get("source_key")) for r in active_manifest_rows()}
    # Map candidate/source keys that are actually active allowlist keys
    allowlist_by_family = {
        normalize_domain(str(r.get("publisher_family") or "")): str(r.get("source_key"))
        for r in active_manifest_rows()
    }
    matrix: list[dict[str, Any]] = []
    for i in range(1, 20):
        dxx = f"D{i:02d}"
        ent = entities.get(dxx) or {"name_en": dxx}
        stats = (per_dxx or {}).get(dxx) or {"ku": 0, "eligible": 0, "kce": 0}
        mapped = list(mapping.get(dxx) or [])
        # Active publishers: intersection of mapped keys with allowlist OR specialized entity presence
        active_pubs: list[str] = []
        for m in mapped:
            # direct key match or publisher family heuristic
            if m in active_keys:
                active_pubs.append(m)
            elif m.startswith("nci") and "nci_cancer_gov" in active_keys:
                active_pubs.append("nci_cancer_gov")
            elif m.startswith("nhlbi") and "nhlbi_health" in active_keys:
                active_pubs.append("nhlbi_health")
            elif m.startswith("niddk") and "niddk_health" in active_keys:
                active_pubs.append("niddk_health")
            elif m.startswith("niams") and "niams_health" in active_keys:
                active_pubs.append("niams_health")
            elif m.startswith("nei") and "nei_eye_health" in active_keys:
                active_pubs.append("nei_eye_health")
            elif m.startswith("nidcr") and "nidcr_oral_health" in active_keys:
                active_pubs.append("nidcr_oral_health")
            elif m.startswith("niosh") and "niosh_occupational" in active_keys:
                active_pubs.append("niosh_occupational")
            elif "medlineplus" in m and "medlineplus_consumer_health" in active_keys:
                active_pubs.append("medlineplus_consumer_health")
            elif m.startswith("nhs") and "nhs_uk_live_well" in active_keys:
                active_pubs.append("nhs_uk_live_well")
            elif "cdc" in m and "cdc_health_lifestyle" in active_keys and "niosh" not in m:
                # lifestyle only — child/ncezid remain inactive
                if m in {"cdc_child_development", "cdc_ncezid_infectious"}:
                    continue
                active_pubs.append("cdc_health_lifestyle")
        active_pubs = sorted(set(active_pubs))
        elig = int(stats.get("eligible") or 0)
        kce = int(stats.get("kce") or 0)
        ku = int(stats.get("ku") or 0)
        depth = depth_class(eligible=elig, kce=kce, active_publishers=len(active_pubs))
        proof = (serving_proof or {}).get(dxx)
        if proof is None:
            if elig > 0:
                proof = "ELIGIBLE_PRESENT"
            elif active_pubs:
                proof = "ACQUIRED_OR_MAPPED_NO_ELIGIBLE"
            else:
                proof = "NO_ACTIVE_PUBLISHER"
        redundancy = (
            "MULTI" if len(active_pubs) >= 2 else ("SINGLE" if len(active_pubs) == 1 else "NONE")
        )
        gap = "NONE" if depth in {"STRONG", "MODERATE"} else ("NEEDS_DEPTH" if active_pubs else "NEEDS_SOURCE")
        # ALS/MS independent tracks
        if dxx in {"D18", "D19"}:
            gap = "ALS_MS_SPECIALIZED_TRACK" if elig > 0 else "ALS_MS_TRACK_THIN"
        matrix.append(
            {
                "dxx": dxx,
                "name": ent.get("name_en"),
                "ku": ku,
                "eligible": elig,
                "kce": kce,
                "active_publishers": active_pubs,
                "serving_proof": proof,
                "depth_state": depth,
                "source_redundancy": redundancy,
                "gap_state": gap,
            }
        )
    # silence unused
    _ = allowlist_by_family
    return matrix


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {s: 0 for s in sorted(ALLOWED_STATUSES)}
    for row in rows:
        st = str(row.get("qualification_status") or "").upper()
        if st in counts:
            counts[st] += 1
        else:
            counts.setdefault("INVALID", 0)
            counts["INVALID"] += 1
    return counts


def assert_no_auto_activation(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        if str(row.get("activation") or "NO").upper() in {"YES", "TRUE", "1"}:
            raise AssertionError(f"AUTO_ACTIVATION_FORBIDDEN:{row.get('candidate_id')}")
        if str(row.get("candidate_id") or "") in ACTIVATION_HARD_BLOCK:
            if str(row.get("activation") or "NO").upper() in {"YES", "TRUE", "1"}:
                raise AssertionError(f"HARD_BLOCK_ACTIVATED:{row.get('candidate_id')}")


def run_foundation_pipeline(
    *,
    live: bool = False,
    include_wave02_gaps: bool = False,
    per_dxx: Optional[dict[str, dict[str, int]]] = None,
    serving_proof: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """
    discover → dedupe registry → qualify → monitor → report.
    NEVER activates sources. NEVER mutates allowlist activation.
    """
    load_candidate_qualification_registry.cache_clear()
    load_trusted_source_manifest.cache_clear()
    load_seed_catalog.cache_clear()

    before_rows = deepcopy(candidate_rows())
    before_counts = status_counts(before_rows)
    discovered = discover_candidates(include_wave02_gaps=include_wave02_gaps)
    merged, merge_stats = merge_discovered_into_registry(discovered, base_rows=before_rows)
    qualified_rows = qualify_registry_rows(
        merged,
        live=live,
        only_statuses={"DISCOVERED", "NEEDS_REVIEW"},
    )
    assert_no_auto_activation(qualified_rows)
    after_counts = status_counts(qualified_rows)
    findings = monitor_active_and_qualified(qualified_rows, live=live, max_subjects=8 if live else 16)
    matrix = build_d01_d19_matrix(per_dxx=per_dxx, serving_proof=serving_proof)

    active_fetch = len(list(active_manifest_rows()))
    owh = next((r for r in qualified_rows if r.get("candidate_id") == "owh_womens_health"), None)
    child = next((r for r in qualified_rows if r.get("candidate_id") == "cdc_child_development"), None)
    ncezid = next((r for r in qualified_rows if r.get("candidate_id") == "cdc_ncezid_infectious"), None)

    depth_groups = {"STRONG": [], "MODERATE": [], "THIN": [], "UNCOVERED": []}
    for row in matrix:
        depth_groups.setdefault(row["depth_state"], []).append(row["dxx"])

    report = {
        "gate": "PD-I5-V1-AUTONOMOUS-SOURCE-DISCOVERY-QUALIFICATION-MONITORING-FOUNDATION-01",
        "auto_activation": "NO",
        "new_source_activation": "NO",
        "candidate_before": len(before_rows),
        "candidate_after": len(qualified_rows),
        "new_candidates": merge_stats["new_candidates"],
        "duplicate_suppressed": merge_stats["duplicate_suppressed"],
        "status_before": before_counts,
        "status_after": after_counts,
        "qualified_total": after_counts.get("QUALIFIED", 0),
        "rejected_total": after_counts.get("REJECTED", 0),
        "needs_review_total": after_counts.get("NEEDS_REVIEW", 0),
        "discovered_total": after_counts.get("DISCOVERED", 0),
        "owh_status": (owh or {}).get("qualification_status", "MISSING"),
        "cdc_child_status": (child or {}).get("qualification_status", "MISSING"),
        "cdc_ncezid_status": (ncezid or {}).get("qualification_status", "MISSING"),
        "owh_activation": (owh or {}).get("activation", "NO"),
        "cdc_child_activation": (child or {}).get("activation", "NO"),
        "cdc_ncezid_activation": (ncezid or {}).get("activation", "NO"),
        "active_source_count": active_fetch,
        "monitor_findings_count": len(findings),
        "monitor_findings": findings[:40],
        "d01_d19_matrix": matrix,
        "strong_domains": depth_groups.get("STRONG") or [],
        "moderate_domains": depth_groups.get("MODERATE") or [],
        "thin_domains": depth_groups.get("THIN") or [],
        "uncovered_domains": depth_groups.get("UNCOVERED") or [],
        "candidates": qualified_rows,
        "generated_at": utc_now_iso(),
    }
    if report["active_source_count"] != 11 and live:
        # Production proof requires stable 11; offline CI may differ if allowlist not loaded same way
        report["active_source_count_note"] = f"observed={report['active_source_count']}"
    return report


def write_ledger(report: dict[str, Any], path: Path) -> None:
    """Persist governed ledger snapshot (no allowlist mutation)."""
    payload = deepcopy(report)
    # Drop bulky candidate bodies optionally kept
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = [
    "ACTIVATION_HARD_BLOCK",
    "MONITOR_CHANGE_KINDS",
    "SEED_CATALOG_RELATIVE",
    "assert_no_auto_activation",
    "build_d01_d19_matrix",
    "candidate_identity_key",
    "discover_candidates",
    "merge_discovered_into_registry",
    "monitor_active_and_qualified",
    "normalize_domain",
    "normalize_url_family",
    "qualify_candidate",
    "qualify_registry_rows",
    "run_foundation_pipeline",
    "status_counts",
    "write_ledger",
]
