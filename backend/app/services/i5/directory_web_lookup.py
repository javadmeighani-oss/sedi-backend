"""On-demand web SEARCH for providers when the governed directory has no good answer (D-016/D-019).

Sedi only searches and prepares what websites publish, according to the user's request. Nothing from the
web is written into the governed directory: results are transient (short in-memory cache), carry the page
link, and are labelled unverified unless the page is on a known listing/official domain.

Privacy: the outbound query is built ONLY from structured fields (entity, specialty, city, province).
The user's message text or any health detail is never sent. Mobile numbers are dropped.
Behind a flag (SEDI_DIRECTORY_WEB_LOOKUP_ENABLED) with a daily cap.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from backend.app.services.i5.iran_directory_p24 import clean_landline

WEB_LOOKUP_SOURCE = "web_lookup"
FLAG = "SEDI_DIRECTORY_WEB_LOOKUP_ENABLED"
MODEL_ENV = "SEDI_DIRECTORY_WEB_LOOKUP_MODEL"
DAILY_CAP_ENV = "SEDI_DIRECTORY_WEB_LOOKUP_DAILY_CAP"
EXTRA_DOMAINS_ENV = "SEDI_DIRECTORY_WEB_TRUSTED_DOMAINS"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_DAILY_CAP = 200
FRESH_DAYS = 30
MAX_RESULTS = 5
MIN_LOCAL_HITS = 2
CACHE_TTL_SECONDS = 24 * 3600
_CACHE_MAX = 256

# Known listing / official domains: results from these are shown without the "unverified site" caveat.
TRUSTED_DOMAINS: dict[str, tuple[str, ...]] = {
    "IR": ("paziresh24.com", "drdr.ir", "doctoreto.com", "nobat.ir", "irimc.org", "behdasht.gov.ir"),
    "*": ("nhs.uk", "who.int"),
}
TRUSTED_SUFFIXES: tuple[str, ...] = (".gov.ir", ".ac.ir", ".gov", ".edu", ".nhs.uk")
# Never a provider listing: search engines, maps share links, generic social posts without a profile.
_BLOCKED_HOSTS = ("google.", "bing.com", "duckduckgo.com", "wikipedia.org", "facebook.com", "twitter.com", "x.com")

_lock = threading.Lock()
_usage: dict[str, int] = {}
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def web_lookup_enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _daily_cap() -> int:
    try:
        return max(0, int(os.getenv(DAILY_CAP_ENV, DEFAULT_DAILY_CAP)))
    except ValueError:
        return DEFAULT_DAILY_CAP


def _take_quota() -> bool:
    today = date.today().isoformat()
    with _lock:
        used = _usage.get(today, 0)
        if used >= _daily_cap():
            return False
        _usage.clear()
        _usage[today] = used + 1
        return True


def _host(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def is_trusted_url(url: str, country: str = "IR") -> bool:
    host = _host(url)
    if not host:
        return False
    extra = tuple(d.strip().lower() for d in os.getenv(EXTRA_DOMAINS_ENV, "").split(",") if d.strip())
    domains = TRUSTED_DOMAINS.get(country.upper(), ()) + TRUSTED_DOMAINS["*"] + extra
    if any(host == d or host.endswith("." + d) for d in domains):
        return True
    return any(host.endswith(s) for s in TRUSTED_SUFFIXES)


def _usable_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = _host(url)
    return parsed.scheme in {"http", "https"} and "." in host and not any(b in host for b in _BLOCKED_HOSTS)


_ENTITY_WORDS = {
    "SPECIALIST": ("doctor", "پزشک"),
    "HOSPITAL": ("hospital", "بیمارستان"),
    "SPECIALTY_CENTER": ("clinic or medical center", "کلینیک یا مرکز درمانی"),
    "LABORATORY": ("medical laboratory", "آزمایشگاه"),
}


def build_query(entity: str, specialty: Optional[str], city: Optional[str], province: Optional[str],
                country: str = "IR") -> Optional[str]:
    """Structured-only query. No city → no lookup (too broad, likely low quality)."""
    if not city:
        return None
    en, fa = _ENTITY_WORDS.get(entity, _ENTITY_WORDS["SPECIALIST"])
    ir = country.upper() == "IR"
    word = fa if ir else en
    what = f"{specialty} {word}" if specialty else word
    where = ", ".join(x for x in (city, province) if x)
    return f"{what} {where}" if ir else f"{what} in {where}"


_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "specialty", "city", "address", "phone", "source_url"],
                "properties": {
                    "name": {"type": "string"},
                    "specialty": {"type": "string"},
                    "city": {"type": "string"},
                    "address": {"type": "string"},
                    "phone": {"type": "string"},
                    "source_url": {"type": "string"},
                },
            },
        }
    },
}


def _instructions(country: str) -> str:
    return (
        "Search the web and return real, currently listed healthcare providers matching the query. "
        "Copy name, specialty, city, address and landline phone exactly as shown on the source page; "
        "use an empty string when a field is not shown. source_url must be the exact page the data came from. "
        "Prefer official sites and well-known medical booking directories"
        + (" in Iran (e.g. paziresh24.com, drdr.ir, doctoreto.com, irimc.org, *.ac.ir hospitals)" if country == "IR" else "")
        + ", but a clinic's or doctor's own website is acceptable when it shows the address or phone. "
        "Never invent providers, phones or addresses. Return at most 8 results."
    )


def _call_web_search(query: str, country: str, client: Any = None) -> list[dict[str, Any]]:
    if client is None:
        from openai import OpenAI

        client = OpenAI()
    resp = client.responses.create(
        model=os.getenv(MODEL_ENV, DEFAULT_MODEL),
        tools=[{"type": "web_search"}],
        instructions=_instructions(country),
        input=query,
        text={"format": {"type": "json_schema", "name": "providers", "schema": _SCHEMA, "strict": True}},
    )
    data = json.loads(getattr(resp, "output_text", "") or "{}")
    return [r for r in (data.get("results") or []) if isinstance(r, dict)]


def validate_results(items: Sequence[dict[str, Any]], *, city: Optional[str], country: str = "IR") -> list[dict[str, Any]]:
    """Real page link + the requested city + something actionable. Mobile numbers dropped.

    Any site is accepted (clinic and doctor sites are legitimate sources); results from known listing or
    official domains are marked trusted and ranked first. Everything is shown as web-published information.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items:
        name = " ".join(str(it.get("name") or "").split())
        url = str(it.get("source_url") or "").strip()
        if not name or not _usable_url(url):
            continue
        address = " ".join(str(it.get("address") or "").split())[:512] or None
        item_city = " ".join(str(it.get("city") or "").split()) or None
        if city and city not in f"{item_city or ''} {address or ''}":
            continue
        phone = clean_landline(it.get("phone"))
        if not (address or phone):
            continue
        key = name + "|" + (item_city or city or "")
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "specialty": " ".join(str(it.get("specialty") or "").split()) or None,
                    "city": item_city or city, "address": address, "phone": phone, "source_url": url,
                    "trusted": is_trusted_url(url, country)})
    out.sort(key=lambda r: not r["trusted"])  # stable: trusted listings first
    return out[:MAX_RESULTS]


def _query_variants(query: str, entity: str, country: str) -> list[str]:
    ir = country.upper() == "IR"
    out = [query, query + (" آدرس و تلفن" if ir else " address phone")]
    if ir and entity == "LABORATORY":
        out.append(query.replace("آزمایشگاه", "آزمایشگاه تشخیص طبی", 1) + " آدرس")
    return out


def search_web_providers(*, entity: str, specialty: Optional[str], city: Optional[str], province: Optional[str],
                         country: str = "IR", client: Any = None) -> list[dict[str, Any]]:
    """One guarded web search (cached 24h per structured query). Never raises, never writes to the DB."""
    if not web_lookup_enabled():
        return []
    query = build_query(entity, specialty, city, province, country)
    if not query:
        return []
    now = time.time()
    with _lock:
        hit = _cache.get(query)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return [dict(r) for r in hit[1]]
    if not _take_quota():
        return []
    results: list[dict[str, Any]] = []
    try:
        raw: list[dict[str, Any]] = []
        for i, variant in enumerate(_query_variants(query, entity, country)):
            if i and not _take_quota():  # web search is non-deterministic: retry with other wording
                break
            raw = _call_web_search(variant, country, client)
            if raw:
                break
        results = validate_results(raw, city=city, country=country)
    except Exception:  # noqa: BLE001 — optional enrichment; the governed answer path must not break
        return []
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[query] = (now, [dict(r) for r in results])
    return results


def web_record_key(source_url: str) -> str:
    return f"{WEB_LOOKUP_SOURCE}:{_host(source_url)}:{hashlib.sha256(source_url.encode('utf-8')).hexdigest()[:24]}"[:128]


def source_domain(canonical_directory_key: str) -> Optional[str]:
    parts = (canonical_directory_key or "").split(":")
    return parts[1] if len(parts) >= 3 and parts[0] == WEB_LOOKUP_SOURCE else None


def is_stale_web_row(source_system_label: Optional[str], last_verified_at: Any) -> bool:
    """Legacy rows stored by the earlier cache design expire after FRESH_DAYS."""
    if source_system_label != WEB_LOOKUP_SOURCE:
        return False
    if isinstance(last_verified_at, str):
        try:
            last_verified_at = datetime.fromisoformat(last_verified_at)
        except ValueError:
            return True
    return not last_verified_at or last_verified_at < datetime.utcnow() - timedelta(days=FRESH_DAYS)
