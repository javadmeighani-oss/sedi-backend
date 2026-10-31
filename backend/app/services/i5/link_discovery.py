"""R-044 step 1 — controlled link discovery for the weekly I5 crawler.

The manifest stays the authority. A source may declare ``link_discovery`` hub pages; the weekly tick reads each hub
once (depth 1, never a site-wide crawl) and keeps a found link ONLY when every gate below holds:

1. same allowed domain and one of the source's own ``allowed_url_patterns``;
2. not a crisis / medication / psychosis / site-chrome page (fixed deny list, a manifest cannot switch it off);
3. it falls inside a reviewed safety lane: ``resolve_specialized_entity_from_url`` gives an entity that the source is
   authorised for (``specialized_serving_eligibility``). Discovery never widens a lane, and a low-risk source has no
   specialized lane, so it never discovers;
4. robots.txt of the host allows it (unreachable robots = the source is skipped, fail closed);
5. within the per-source and per-run budget.

Found URLs are kept in ``knowledge_sources.crawl_policy_json["discovered_urls"]`` (JSON, no migration) and fetched by
the same weekly path as the manifest URLs, through the same extraction, D23 boundary and eligibility gates.
Flag ``SEDI_I5_LINK_DISCOVERY_ENABLED`` (default OFF): off = nothing is discovered AND stored discoveries are not
fetched. Any error degrades to the plain weekly run (fail-open for the crawler, fail-closed for what is admitted).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Mapping, Optional
from urllib import robotparser
from urllib.parse import urljoin, urlparse

from backend.app.services.i5.adapters.base import AdapterFrameworkError, canonical_url
from backend.app.services.i5.governed_specialized_entity_eligibility import (
    resolve_specialized_entity_from_url,
    specialized_allowed_entities_for_source,
)
from backend.app.services.i5.trusted_source_manifest import active_manifest_rows

logger = logging.getLogger(__name__)

PACKAGE_ID = "I5-R044-LINK-DISCOVERY-V1"
LINK_DISCOVERY_ENV = "SEDI_I5_LINK_DISCOVERY_ENABLED"

MAX_NEW_URLS_PER_RUN = 25
DEFAULT_MAX_NEW_URLS_PER_CYCLE = 10
DEFAULT_MAX_DISCOVERED_URLS = 40
MAX_HUBS_PER_SOURCE = 8
MAX_HUB_BYTES = 1_048_576

# Never admitted, whatever a manifest says: crisis belongs to I4, medication choice is never Sedi's, and these clinical
# areas need care beyond consumer education.
CONTENT_DENY_TOKENS: tuple[str, ...] = (
    "suicid",
    "self-harm",
    "selfharm",
    "self-injur",
    "crisis",
    "urgent",
    "emergency",
    "overdose",
    "psychosis",
    "psychotic",
    "schizophren",
    "personality-disorder",
    "personalitydisorder",
    "eating-disorder",
    "eatingdisorder",
    "anorexia",
    "bulimia",
    "binge",
    "munchausen",
    "fabricated",
    "dissociative",
    "antidepressant",
    "medicine",
    "medication",
    "drug",
    "abuse",
)
# Site chrome and tools, not knowledge.
CHROME_DENY_TOKENS: tuple[str, ...] = (
    "accessibility",
    "contact-us",
    "privacy",
    "cookie",
    "site-map",
    "sitemap",
    "terms-and-conditions",
    "quiz",
    "sign-up",
    "signup",
    "login",
    "search",
    "feedback",
    "newsletter",
)

FetchPage = Callable[[str, str], tuple[int, str, bytes, str]]
LoadRobots = Callable[[str], Optional[robotparser.RobotFileParser]]


def link_discovery_enabled() -> bool:
    return os.environ.get(LINK_DISCOVERY_ENV, "").strip().lower() in {"1", "true", "yes"}


def url_key(url: str) -> str:
    """Comparison key: lower-case, no query/fragment, no trailing slash."""
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "/").rstrip("/").lower()
    return f"{host}{path}"


@dataclass(frozen=True)
class DiscoveryConfig:
    hub_urls: tuple[str, ...]
    max_new_urls_per_cycle: int
    max_discovered_urls: int
    exclude_url_tokens: tuple[str, ...]


def discovery_config(row: Mapping[str, Any]) -> Optional[DiscoveryConfig]:
    """Validated ``link_discovery`` block of a manifest row, or None (no discovery for this source)."""
    raw = row.get("link_discovery")
    if not isinstance(raw, Mapping):
        return None
    hubs: list[str] = []
    for hub in raw.get("hub_urls") or []:
        hub = str(hub or "").strip()
        if hub and _host_allowed(hub, row) and _pattern_allowed(hub, row) and hub not in hubs:
            hubs.append(hub)
    if not hubs:
        return None

    def _int(name: str, default: int, ceiling: int) -> int:
        try:
            value = int(raw.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(0, min(value, ceiling))

    return DiscoveryConfig(
        hub_urls=tuple(hubs[:MAX_HUBS_PER_SOURCE]),
        max_new_urls_per_cycle=_int("max_new_urls_per_cycle", DEFAULT_MAX_NEW_URLS_PER_CYCLE, MAX_NEW_URLS_PER_RUN),
        max_discovered_urls=_int("max_discovered_urls", DEFAULT_MAX_DISCOVERED_URLS, 200),
        exclude_url_tokens=tuple(str(t).strip().lower() for t in (raw.get("exclude_url_tokens") or []) if str(t).strip()),
    )


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                self.hrefs.append(value)


def extract_links(html: str, base_url: str) -> list[str]:
    """Absolute https links of a page, in page order, without query/fragment, de-duplicated."""
    collector = _AnchorCollector()
    try:
        collector.feed(html or "")
    except Exception:  # noqa: BLE001 — a broken hub yields no links, never an error
        return []
    out: list[str] = []
    seen: set[str] = set()
    for href in collector.hrefs:
        absolute = urljoin(base_url, href.strip())
        parsed = urlparse(absolute)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            continue
        try:
            url = canonical_url(parsed._replace(query="", fragment="").geturl())
        except AdapterFrameworkError:
            continue
        key = url_key(url)
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
    return out


def _host_allowed(url: str, row: Mapping[str, Any]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    domain = str(row.get("allowed_domain") or "").strip().lower().lstrip(".")
    return bool(domain) and (host == domain or host.endswith("." + domain))


def _pattern_allowed(url: str, row: Mapping[str, Any]) -> bool:
    for pattern in row.get("allowed_url_patterns") or []:
        try:
            if re.match(str(pattern), url):
                return True
        except re.error:
            continue
    return False


def admit_discovered_url(
    url: str,
    row: Mapping[str, Any],
    *,
    allowed_entities: Iterable[str],
    known_keys: Iterable[str] = (),
    exclude_url_tokens: Iterable[str] = (),
) -> tuple[bool, str, Optional[str]]:
    """(admitted, reason, lane entity id). Pure: no network, no DB."""
    if not url or not url.startswith("https://"):
        return False, "NOT_HTTPS", None
    if not _host_allowed(url, row):
        return False, "DOMAIN_NOT_ALLOWED", None
    if not _pattern_allowed(url, row):
        return False, "PATTERN_NOT_ALLOWED", None
    low = url.lower()
    if any(token in low for token in CONTENT_DENY_TOKENS):
        return False, "CONTENT_DENY", None
    if any(token in low for token in CHROME_DENY_TOKENS):
        return False, "CHROME_DENY", None
    if any(token in low for token in exclude_url_tokens):
        return False, "SOURCE_EXCLUDE", None
    spec = resolve_specialized_entity_from_url(url)
    if spec is None or spec.entity_id not in set(allowed_entities):
        return False, "NO_SAFETY_LANE", None
    if url_key(url) in set(known_keys):
        return False, "ALREADY_KNOWN", spec.entity_id
    return True, "ADMITTED", spec.entity_id


def _default_fetch_page(http_get: Any = None) -> FetchPage:
    from backend.app.services.i5.adapters.live_transport import fetch_live_https

    def fetch(url: str, allowed_domain: str) -> tuple[int, str, bytes, str]:
        resp = fetch_live_https(
            url=url,
            allowed_domain=allowed_domain,
            max_bytes=MAX_HUB_BYTES,
            http_get=http_get,
        )
        return int(resp.status_code), str(resp.content_type or ""), bytes(resp.body or b""), str(resp.final_url or url)

    return fetch


def _default_load_robots(http_get: Any = None) -> LoadRobots:
    import requests

    from backend.app.services.gate3.knowledge_source_fetcher import USER_AGENT

    getter = http_get or requests.get

    def load(host: str) -> Optional[robotparser.RobotFileParser]:
        try:
            resp = getter(f"https://{host}/robots.txt", timeout=8, headers={"User-Agent": USER_AGENT})
            if int(resp.status_code) >= 400:
                return None
            parser = robotparser.RobotFileParser()
            parser.parse(str(resp.text or "").splitlines())
            return parser
        except Exception:  # noqa: BLE001 — unreachable robots = skip the source (fail closed)
            return None

    return load


def _robots_allows(parser: robotparser.RobotFileParser, url: str) -> bool:
    from backend.app.services.gate3.knowledge_source_fetcher import USER_AGENT

    return parser.can_fetch(USER_AGENT, url)


@dataclass
class SourceDiscovery:
    source_key: str
    status: str
    hubs_checked: int = 0
    admitted: list[dict[str, str]] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "status": self.status,
            "hubs_checked": self.hubs_checked,
            "admitted": len(self.admitted),
            "rejected": dict(sorted(self.rejected.items())),
        }


def discover_for_row(
    row: Mapping[str, Any],
    *,
    known_keys: Iterable[str],
    budget: int,
    fetch_page: FetchPage,
    load_robots: LoadRobots,
    robots_cache: Optional[dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> SourceDiscovery:
    """Read the hubs of one manifest row and return the admitted links (network, no DB)."""
    key = str(row.get("source_key") or "")
    cfg = discovery_config(row)
    if cfg is None:
        return SourceDiscovery(key, "NO_DISCOVERY_CONFIG")
    allowed = specialized_allowed_entities_for_source(key)
    if not allowed:
        return SourceDiscovery(key, "NO_SAFETY_LANE_FOR_SOURCE")
    if budget <= 0:
        return SourceDiscovery(key, "BUDGET_EXHAUSTED")
    result = SourceDiscovery(key, "OK")
    known = {url_key(u) for u in cfg.hub_urls} | set(known_keys)
    cache = robots_cache if robots_cache is not None else {}
    stamp = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    domain = str(row.get("allowed_domain") or "").strip().lower()

    def _robots(url: str) -> Optional[robotparser.RobotFileParser]:
        host = (urlparse(url).hostname or "").lower()
        if host not in cache:
            cache[host] = load_robots(host)
        return cache[host]

    def _reject(reason: str) -> None:
        result.rejected[reason] = result.rejected.get(reason, 0) + 1

    for hub in cfg.hub_urls:
        if len(result.admitted) >= budget:
            break
        robots = _robots(hub)
        if robots is None:
            result.status = "ROBOTS_UNAVAILABLE"
            return result
        if not _robots_allows(robots, hub):
            _reject("HUB_ROBOTS_DISALLOW")
            continue
        try:
            status, content_type, body, final_url = fetch_page(hub, domain)
        except AdapterFrameworkError as exc:
            _reject(f"HUB_{exc.category}")
            continue
        except Exception:  # noqa: BLE001
            _reject("HUB_FETCH_FAILED")
            continue
        if status != 200 or "html" not in (content_type or "").lower():
            _reject(f"HUB_HTTP_{status}")
            continue
        result.hubs_checked += 1
        for link in extract_links(body.decode("utf-8", errors="replace"), final_url or hub):
            ok, reason, entity = admit_discovered_url(
                link,
                row,
                allowed_entities=allowed,
                known_keys=known,
                exclude_url_tokens=cfg.exclude_url_tokens,
            )
            if ok and not _robots_allows(robots, link):
                ok, reason = False, "ROBOTS_DISALLOW"
            if not ok:
                _reject(reason)
                continue
            known.add(url_key(link))
            result.admitted.append({"url": link, "entity_id": str(entity), "via": hub, "discovered_at": stamp})
            if len(result.admitted) >= budget:
                break
    return result


def _load_policy(raw: Optional[str]) -> dict[str, Any]:
    try:
        policy = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return policy if isinstance(policy, dict) else {}


def discovered_entries(policy: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [e for e in (policy.get("discovered_urls") or []) if isinstance(e, Mapping) and e.get("url")]


def discovered_urls_for_cycle(row: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    """Stored discoveries to fetch this cycle, re-checked against TODAY's manifest and lanes (no network).

    Flag off, a narrowed pattern, a removed lane or a new deny token drops a URL from the fetch set at once.
    """
    if not link_discovery_enabled():
        return []
    cfg = discovery_config(row)
    if cfg is None:
        return []
    allowed = specialized_allowed_entities_for_source(str(row.get("source_key") or ""))
    if not allowed:
        return []
    controlled = {url_key(u) for u in (policy.get("controlled_urls") or [])}
    out: list[str] = []
    for entry in discovered_entries(policy)[: cfg.max_discovered_urls]:
        url = str(entry["url"])
        ok, _, _ = admit_discovered_url(
            url,
            row,
            allowed_entities=allowed,
            known_keys=controlled,
            exclude_url_tokens=cfg.exclude_url_tokens,
        )
        if ok and url_key(url) not in {url_key(u) for u in out}:
            out.append(url)
    return out


def merge_discovery_state(new_policy: dict[str, Any], previous_raw: Optional[str]) -> dict[str, Any]:
    """Keep stored discoveries when the activation workflow rewrites a source's crawl policy."""
    previous = _load_policy(previous_raw)
    for name in ("discovered_urls", "link_discovery_last"):
        if name in previous:
            new_policy[name] = previous[name]
    return new_policy


@dataclass
class LinkDiscoveryReport:
    sources: list[dict[str, Any]] = field(default_factory=list)
    admitted_total: int = 0

    def summary(self) -> dict[str, Any]:
        return {"package_id": PACKAGE_ID, "admitted_total": self.admitted_total, "sources": self.sources}


def run_link_discovery(
    db: Any,
    models: Any,
    *,
    fetch_page: Optional[FetchPage] = None,
    load_robots: Optional[LoadRobots] = None,
    http_get: Any = None,
    now: Optional[datetime] = None,
    max_new_urls_per_run: int = MAX_NEW_URLS_PER_RUN,
) -> LinkDiscoveryReport:
    """Discover for every active manifest row with ``link_discovery`` and store the admitted URLs."""
    fetch = fetch_page or _default_fetch_page(http_get)
    robots = load_robots or _default_load_robots(http_get)
    robots_cache: dict[str, Any] = {}
    report = LinkDiscoveryReport()
    remaining = max(0, int(max_new_urls_per_run))
    stamp = (now or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    for row in active_manifest_rows():
        cfg = discovery_config(row)
        if cfg is None:
            continue
        key = str(row["source_key"])
        ks = db.query(models.KnowledgeSource).filter(models.KnowledgeSource.slug == key).one_or_none()
        if ks is None or not bool(ks.source_fetch_enabled):
            report.sources.append(SourceDiscovery(key, "SOURCE_NOT_ACTIVE").summary())
            continue
        policy = _load_policy(ks.crawl_policy_json)
        stored = discovered_entries(policy)
        known = {url_key(u) for u in (policy.get("controlled_urls") or [])} | {url_key(str(e["url"])) for e in stored}
        budget = min(cfg.max_new_urls_per_cycle, cfg.max_discovered_urls - len(stored), remaining)
        found = discover_for_row(
            row,
            known_keys=known,
            budget=budget,
            fetch_page=fetch,
            load_robots=robots,
            robots_cache=robots_cache,
            now=now,
        )
        summary = found.summary()
        policy["discovered_urls"] = stored + found.admitted
        policy["link_discovery_last"] = {"at": stamp, **{k: v for k, v in summary.items() if k != "source_key"}}
        ks.crawl_policy_json = json.dumps(policy, sort_keys=True)
        remaining -= len(found.admitted)
        report.admitted_total += len(found.admitted)
        report.sources.append(summary)
    db.flush()
    return report


def maybe_run_link_discovery(db: Any, models: Any, *, http_get: Any = None) -> Optional[LinkDiscoveryReport]:
    """Weekly-tick hook: runs only with multisource + discovery flags ON; never breaks the weekly run."""
    multisource = os.environ.get("SEDI_I5_MULTISOURCE_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    if not (multisource and link_discovery_enabled()) or db is None or models is None:
        return None
    nested = None
    try:
        begin_nested = getattr(db, "begin_nested", None)
        nested = begin_nested() if callable(begin_nested) else None
        report = run_link_discovery(db, models, http_get=http_get)
        if nested is not None:
            nested.commit()
        logger.info("i5_link_discovery %s", json.dumps(report.summary(), sort_keys=True))
        return report
    except Exception as exc:  # noqa: BLE001 — discovery is optional; the weekly run goes on without it
        if nested is not None:
            try:
                nested.rollback()
            except Exception:  # noqa: BLE001
                pass
        logger.warning("i5_link_discovery_failed %s", type(exc).__name__)
        return None


__all__ = [
    "PACKAGE_ID",
    "LINK_DISCOVERY_ENV",
    "CONTENT_DENY_TOKENS",
    "CHROME_DENY_TOKENS",
    "DiscoveryConfig",
    "LinkDiscoveryReport",
    "SourceDiscovery",
    "admit_discovered_url",
    "discover_for_row",
    "discovered_entries",
    "discovered_urls_for_cycle",
    "discovery_config",
    "extract_links",
    "link_discovery_enabled",
    "maybe_run_link_discovery",
    "merge_discovery_state",
    "run_link_discovery",
    "url_key",
]
