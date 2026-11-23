"""On-demand web SEARCH for providers when the governed directory has no good answer (D-016/D-019).

Sedi only searches and prepares what websites publish, according to the user's request. Nothing from the
web is written into the governed directory: results are transient (short in-memory cache), carry the page
link, and are labelled unverified unless the page is on a known listing/official domain.

Privacy: the outbound query is built ONLY from structured fields (entity, specialty, city, province).
The user's message text or any health detail is never sent. Mobile numbers are dropped.
Behind a flag (SEDI_DIRECTORY_WEB_LOOKUP_ENABLED) with a daily cap.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from backend.app.services.i5 import page_facts as _page_facts
from backend.app.services.i5.iran_directory_p24 import clean_landline  # noqa: F401  (kept for importers)
from backend.app.services.i5.iran_places import mentions as _mentions
from backend.app.services.i5.iran_places import normalize as _norm_place

WEB_LOOKUP_SOURCE = "web_lookup"
FLAG = "SEDI_DIRECTORY_WEB_LOOKUP_ENABLED"
MODEL_ENV = "SEDI_DIRECTORY_WEB_LOOKUP_MODEL"
DAILY_CAP_ENV = "SEDI_DIRECTORY_WEB_LOOKUP_DAILY_CAP"
EXTRA_DOMAINS_ENV = "SEDI_DIRECTORY_WEB_TRUSTED_DOMAINS"
DEFAULT_MODEL = "gpt-6-luna"  # R-117 (Javad 2026-11-23): Luna for provider search + nearby geography (eval D-505: phone-verified 66.7% vs 19.5%, address 75.6% vs 33.8%)
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

logger = logging.getLogger(__name__)
SPEC_FILTER_DISABLED_ENV = "SEDI_DIRECTORY_SPEC_FILTER_DISABLED"  # kill switch (code default ON)
REQUEST_BUDGET = 8  # R-114 am.1: web searches ONE user request may spend (area + the nearest-area rings together)
REQUEST_SECONDS = 60.0  # R-117: ... and the seconds it may spend (Luna answers in ~25 s: rings must never run for minutes)
_BUDGET: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar("sedi_web_budget", default=None)


@contextmanager
def request_budget(limit: int = REQUEST_BUDGET, seconds: float = REQUEST_SECONDS):
    """Scope of one user request: every provider web search inside it counts against ``limit``; the yielded dict is the request's
    telemetry (queries spent, results dropped for the wrong specialty) - structured counters only, never user data."""
    state = {"limit": int(limit), "queries": 0, "dropped": 0, "deadline": time.monotonic() + float(seconds)}
    token = _BUDGET.set(state)
    try:
        yield state
    finally:
        _BUDGET.reset(token)


def _take_request_budget() -> bool:
    state = _BUDGET.get()
    if state is None:
        return True
    if state["queries"] >= state["limit"] or time.monotonic() >= state["deadline"]:
        return False
    state["queries"] += 1
    return True


def budget_left() -> bool:
    state = _BUDGET.get()
    return state is None or (state["queries"] < state["limit"] and time.monotonic() < state["deadline"])


def remaining_seconds() -> Optional[float]:
    """Seconds left of the request's time budget (None = no budget scope); the provider call gets this as its own timeout."""
    state = _BUDGET.get()
    return None if state is None else max(0.0, state["deadline"] - time.monotonic())


def search_model() -> str:
    """The provider-search model: the env override, else Luna (R-117)."""
    return (os.getenv(MODEL_ENV) or "").strip() or DEFAULT_MODEL


def call_options() -> dict:
    """Extra kwargs for the provider call inside a request budget: a timeout no longer than the seconds left (at least 5)."""
    left = remaining_seconds()
    return {} if left is None else {"timeout": max(5.0, left)}


def new_client() -> Any:
    """OpenAI client for the provider/geography calls. Inside a request budget the SDK's own retries are OFF (a timed-out call would
    otherwise be retried twice with the same timeout and overrun the deadline); outside a budget the SDK default is kept."""
    from openai import OpenAI

    return OpenAI() if remaining_seconds() is None else OpenAI(max_retries=0)


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
    "PHARMACY": ("pharmacy", "داروخانه"),
}


def build_query(entity: str, specialty: Optional[str], city: Optional[str], province: Optional[str],
                country: str = "IR", area: Optional[str] = None, qualifiers: Sequence[str] = ()) -> Optional[str]:
    """Structured-only query. No place at all (neither city nor area) -> no lookup (too broad). R-114 am.1: a doctor query reads like the
    booking sites name it («متخصص گوارش در بومهن, تهران»); an area WITHOUT a city is still a place (it used to skip the search)."""
    if not (city or area):
        return None
    en, fa = _ENTITY_WORDS.get(entity, _ENTITY_WORDS["SPECIALIST"])
    ir = country.upper() == "IR"
    word = fa if ir else en
    doctor_by_specialty = entity == "SPECIALIST" and bool(specialty) and ir
    if doctor_by_specialty:
        what = f"متخصص {specialty}"
    else:
        what = f"{specialty} {word}" if specialty else word
    if "24h" in qualifiers:
        what += " شبانه‌روزی" if ir else " open 24 hours"
    if "high_rating" in qualifiers:
        what += " با امتیاز بالا" if ir else " highly rated"
    where = ", ".join(x for x in (area, city, province) if x)
    if doctor_by_specialty:
        return f"{what} در {where}"
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
                "required": ["name", "specialty", "city", "address", "phone", "source_url", "visit_days", "rating", "rating_count"],
                "properties": {
                    "name": {"type": "string"},
                    "specialty": {"type": "string"},
                    "city": {"type": "string"},
                    "address": {"type": "string"},
                    "phone": {"type": "string"},
                    "source_url": {"type": "string"},
                    "visit_days": {"type": "array", "items": {"type": "string"}},
                    "rating": {"type": "string"},
                    "rating_count": {"type": "string"},
                },
            },
        }
    },
}


def _instructions(country: str) -> str:
    return (
        "Search the web and return real, currently listed healthcare providers matching the query. "
        "Copy name, specialty, city, address and phone number exactly as the source page publishes them; "
        "visit_days = the weekdays the page says the doctor visits (empty list when not shown); rating = the average score shown "
        "(e.g. 4.5 of 5) and rating_count = the number of patient reviews, both as plain numbers. "
        "Use an empty string (or empty list) when a field is not shown. source_url must be the exact page the data came from. "
        "Prefer official sites and well-known medical booking directories"
        + (" in Iran (e.g. paziresh24.com, drdr.ir, doctoreto.com, irimc.org, *.ac.ir hospitals)" if country == "IR" else "")
        + ", but a clinic's or doctor's own website is acceptable when it shows the address or phone. "
        "When the query names a neighbourhood or district, return providers located in it or nearby first. "
        "Never invent providers, phones or addresses. Return at most 8 results."
    )


def _call_web_search(query: str, country: str, client: Any = None) -> list[dict[str, Any]]:
    if client is None:
        client = new_client()
    resp = client.responses.create(
        model=search_model(),
        tools=[{"type": "web_search"}],
        instructions=_instructions(country),
        input=query,
        text={"format": {"type": "json_schema", "name": "providers", "schema": _SCHEMA, "strict": True}},
        **call_options(),
    )
    data = json.loads(getattr(resp, "output_text", "") or "{}")
    return [r for r in (data.get("results") or []) if isinstance(r, dict)]


def validate_results(items: Sequence[dict[str, Any]], *, city: Optional[str], country: str = "IR",
                     area: Optional[str] = None) -> list[dict[str, Any]]:
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
        place_text = _norm_place(f"{item_city or ''} {address or ''}")
        area_hit = bool(area and _norm_place(area) in place_text)
        # spacing/half-space tolerant: «تهرانپارس» == «تهران‌پارس»; a neighbourhood match is enough (R-089)
        if city and not _mentions(place_text, city) and not area_hit:
            continue
        if not city and area and not area_hit:
            continue  # R-114: area-only search - the result must name that area
        # ...unless the result explicitly names ANOTHER city (e.g. «شیراز، منطقه ۸» for Tehran's district 8) - Codex P2
        if city and item_city and not _mentions(_norm_place(item_city), city) and not (
            area and _norm_place(area) in _norm_place(item_city)
        ):
            continue
        phone = _page_facts.published_phone(it.get("phone"))
        if not (address or phone):
            continue
        key = name + "|" + (item_city or city or "")
        if key in seen:
            continue
        seen.add(key)
        days = it.get("visit_days")
        out.append({"name": name, "specialty": " ".join(str(it.get("specialty") or "").split()) or None,
                    "city": item_city or city, "address": address, "phone": phone, "source_url": url,
                    "trusted": is_trusted_url(url, country),
                    "visit_days": [str(d)[:24] for d in days][:7] if isinstance(days, list) else [],
                    "rating": str(it.get("rating") or "")[:8], "rating_count": str(it.get("rating_count") or "")[:8]})
    out.sort(key=lambda r: not r["trusted"])  # stable: trusted listings first
    return out[:MAX_RESULTS]


_VERIFY_WORKERS = 5
RATING_PRIOR_WEIGHT = 10  # reviews' worth of doubt added to every average


def _score(r: dict[str, Any], *, specialty: Optional[str], area: Optional[str], qualifiers: Sequence[str]) -> float:
    score = 3.0 if r.get("trusted") else 0.0
    score += 1.0 if r.get("page_read") else 0.0
    score += 2.0 if r.get("phone_status") == "verified" else 0.0
    score += 1.0 if r.get("address_verified") else 0.0
    score += 2.0 if "area" in (r.get("why") or ()) else 0.0
    score += 1.0 if "spec" in (r.get("why") or ()) else 0.0
    score += 0.5 if r.get("visit_days") or r.get("next_turn") else 0.0
    avg, cnt = r.get("rating_avg"), r.get("rating_count") or 0
    if avg:
        # R-114 am.1 (Javad: Sedi recommends by the patients' ratings): shrink the average toward 4.0 by how few reviews back it
        weight = 1.5 if "high_rating" in qualifiers else 0.6
        shrunk = (float(avg) * cnt + 4.0 * RATING_PRIOR_WEIGHT) / (cnt + RATING_PRIOR_WEIGHT)
        score += weight * shrunk
    if "24h" in qualifiers:
        score += 3.0 if r.get("open_24h") else (-2.0 if r.get("page_read") else 0.0)
    return score


def verify_and_rank(results: list[dict[str, Any]], *, specialty: Optional[str] = None, area: Optional[str] = None,
                    qualifiers: Sequence[str] = (), fetch: Any = None) -> list[dict[str, Any]]:
    """J3-b: read each result's own page (SSRF-safe, parallel, capped), keep only what the page confirms, rank, and say WHY.

    A page that was read and does NOT contain the claimed number/address is dropped (likely mis-copied or invented); a page that
    could not be read keeps the claim but marked unchecked (never silently trusted). Never raises."""
    if not results:
        return results
    if os.getenv("SEDI_DIRECTORY_PAGE_VERIFY_DISABLED", "").strip().lower() in {"1", "true", "yes", "on"}:  # kill switch (code default ON)
        return [dict(r, phone_status="unchecked" if r.get("phone") else None) for r in results]
    from concurrent.futures import ThreadPoolExecutor

    kwargs = {"fetch": fetch} if fetch is not None else {}
    try:
        with ThreadPoolExecutor(max_workers=min(_VERIFY_WORKERS, len(results))) as pool:
            checks = list(pool.map(lambda r: _page_facts.verify_result(r, **kwargs), results))
    except Exception:  # noqa: BLE001
        return results
    out: list[dict[str, Any]] = []
    for r, v in zip(results, checks):
        row = dict(r)
        if v.read and not v.phone and not v.address_verified:
            continue  # the page was read and confirms neither the number nor the address: not shown
        row.update(phone=v.phone, phone_status=v.phone_status, address=v.address, address_verified=v.address_verified,
                   visit_days=list(v.visit_days), next_turn=v.next_turn, rating_avg=v.rating_avg, rating_count=v.rating_count,
                   checked_on=v.checked_on, page_read=v.read)
        row["open_24h"] = bool(v.open_24h)
        why: list[str] = []
        place = _norm_place(f"{row.get('city') or ''} {row.get('address') or ''}")
        if specialty and _norm_place(specialty)[:4] and (
            _norm_place(specialty)[:4] in _norm_place(str(row.get("specialty") or "")) or _norm_place(specialty) in _norm_place(row["name"])
        ):
            why.append("spec")
        if area and _norm_place(area) in place:
            why.append("area")
        if row.get("rating_avg") and (row.get("rating_count") or 0) >= 10 and float(row["rating_avg"]) >= 4.0:
            why.append("rating")
        if "24h" in qualifiers and row["open_24h"]:
            why.append("open24")
        if row["phone_status"] == "verified" or row["address_verified"]:
            why.append("page_checked")
        row["why"] = tuple(why)
        out.append(row)
    out.sort(key=lambda r: -_score(r, specialty=specialty, area=area, qualifiers=qualifiers))
    return out[:MAX_RESULTS]



def _query_variants(query: str, entity: str, country: str) -> list[str]:
    ir = country.upper() == "IR"
    out = [query, query + (" آدرس و تلفن" if ir else " address phone")]
    if ir and entity == "LABORATORY":
        out.append(query.replace("آزمایشگاه", "آزمایشگاه تشخیص طبی", 1) + " آدرس")
    if ir:  # R-089: last try aimed at the Iranian booking / listing sites
        site = query + " نوبت‌دهی پذیرش۲۴ دکترتو دکتر دکتر"
        if entity == "SPECIALIST":  # R-114 am.1: for a doctor the booking sites are what find the doctor pages - they come SECOND
            out.insert(1, site)
        else:
            out.append(site)
    return out


def search_web_providers(*, entity: str, specialty: Optional[str], city: Optional[str], province: Optional[str],
                         country: str = "IR", client: Any = None, area: Optional[str] = None,
                         qualifiers: Sequence[str] = ()) -> list[dict[str, Any]]:
    """One guarded web search (cached 24h per structured query). Never raises, never writes to the DB."""
    if not web_lookup_enabled():
        return []
    query = build_query(entity, specialty, city, province, country, area=area, qualifiers=tuple(qualifiers or ()))
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
    incomplete = False  # the budget / quota stopped the search before every wording was tried: a miss then must not be remembered
    try:
        raw: list[dict[str, Any]] = []
        for i, variant in enumerate(_query_variants(query, entity, country)):
            if i and not _take_quota():  # web search is non-deterministic: retry with other wording
                incomplete = True
                break
            if not _take_request_budget():  # R-114 am.1: one request never drains the daily cap (area + rings share this budget)
                incomplete = True
                break
            found = _call_web_search(variant, country, client)
            # the specialty filter runs on the RAW answer, BEFORE the candidate limit and INSIDE the retry loop: wrong specialties neither use up
            # the slots nor end the search - the other wordings (booking sites, address) are still tried (Codex P2, PR 213)
            raw = _only_the_specialty(found, entity, specialty)
            if raw:
                break
        results = validate_results(raw, city=city, country=country, area=area)
        results = verify_and_rank(results, specialty=specialty, area=area, qualifiers=tuple(qualifiers or ()))
    except Exception:  # noqa: BLE001 — optional enrichment; the governed answer path must not break
        return []
    if incomplete and not results:
        return results  # not cached: a fresh request with budget left may still find the provider
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[query] = (now, [dict(r) for r in results])
    return results


def _only_the_specialty(results: list[dict[str, Any]], entity: str, specialty: Optional[str]) -> list[dict[str, Any]]:
    """R-114 am.1 (Javad E2): a doctor result must BE the requested specialty (its own specialty text or name says so); a pediatrician for a
    gastro request is dropped, not merely ranked lower. Entities other than doctors and unknown specialty labels are never filtered."""
    if entity != "SPECIALIST" or not specialty or os.getenv(SPEC_FILTER_DISABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}:
        return results
    from backend.app.services.i5 import specialty_lexicon as _lex

    kept = [r for r in results if _lex.result_matches_specialty(specialty, r.get("specialty"), r.get("name"))]
    state = _BUDGET.get()
    if state is not None:
        state["dropped"] += len(results) - len(kept)
    return kept


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
