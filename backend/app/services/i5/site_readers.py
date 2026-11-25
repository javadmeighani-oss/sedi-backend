"""R-114 am.1 / R-116 am.1 (Javad 2026-11-23): Sedi READS the booking sites Javad named - real data, not a model's guess.

Investigation (D-503): the provider web_search tool returns NOTHING from Doctoreto / Paziresh24 / Doctor-Doctor / Saina / Doctor-Yab, but the
server's own page reader CAN read their public pages, and the pages carry structured data:

  * Doctoreto   ``/doctors/speciality/{slug}/city/{city}``  - Next.js ``__NEXT_DATA__``: 25 doctors per page with address, coordinates, rating
                (average, count, satisfaction %), next free time, profile route; plus the nearby cities / neighbourhoods of the page.
  * Paziresh24  ``/s/{city}/{expertise}/``                  - Next.js ``__NEXT_DATA__``: 20 results per page with address, centers, satisfaction %,
                number of ratings, visits, waiting time, profile URL.

This module is the ONE reader for them: build the listing URLs, fetch through ``safe_fetch.fetch_page`` (public https only, robots honoured,
size/time capped - R-045), parse the embedded JSON into one normalised ``SiteProvider``, rank by the patients' ratings (a shrunk average, so a
5.0 from two reviews does not beat 4.7 from 400) and distance, page through the ranking FIVE at a time (Javad: five per introduction, the next
five when the first do not suit). Reading is LIVE and transient (cached a short while in memory); nothing is stored here (the library of
providers Sedi's users actually used is a separate, consented step). Fail-open: any site that cannot be read is reported and skipped.

Reading goes behind ``SEDI_SITE_READERS_ENABLED`` (default OFF) when wired into the chat; the eval harness calls it directly.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence
from urllib.parse import quote, urlparse

from backend.app.services.i5 import safe_fetch

logger = logging.getLogger(__name__)

ENABLED_ENV = "SEDI_SITE_READERS_ENABLED"  # default OFF: the chat reads the booking sites only when this is switched on
MIN_GAP_SECONDS = 1.0  # polite reading: a burst of requests can make a site answer with empty pages (D-503)
MAX_PAGES = 3  # listing pages read for one request (20-25 providers each) when too few qualified providers were found
SPARE = 3  # candidates kept beyond the five, to replace any whose profile page fails the check
READ_TOTAL_SECONDS = 24.0  # all listing pages of ONE request
VERIFY_BUDGET_SECONDS = 10.0  # the profile-page checks of ONE request; beyond it the remaining candidates are shown unchecked (fail-open)
VERIFY_TTL_SECONDS = 24 * 3600  # a checked profile is not fetched again for a day (Javad 2026-11-25: option C - slow only the first time)
VERIFY_ENV = "SEDI_SITE_LINK_VERIFY_ENABLED"  # default ON; «false» turns the profile check off
PAGE_SIZE = 5  # providers per introduction (Javad); the next five on request
CACHE_TTL_SECONDS = 6 * 3600
READ_TIMEOUT_SECONDS = 14.0  # the whole parallel read of one request
RATING_PRIOR = 4.0  # shrink every average toward this by how few reviews back it
RATING_PRIOR_WEIGHT = 10
_NEXT_DATA = re.compile(r"<script id=.__NEXT_DATA__.[^>]*>")

SITE_DOCTORETO = "doctoreto.com"
SITE_P24 = "paziresh24.com"

# canonical specialty (specialty_lexicon) -> the slug each site uses in its listing URL (verified against the live sites 2026-11-23)
P24_SLUGS = {
    "ارتوپدی": "orthopedics", "زنان": "obstetrics-gynecology", "چشم": "ophthalmology", "گوارش": "gastroenterology", "اورولوژی": "urology",
    "غدد": "endocrinology", "قلب": "cardiovascular", "داخلی": "internal", "دندانپزشکی": "dental-oral", "پوست": "dermatology",
    "جراحی عمومی": "surgery", "اطفال": "pediatrics", "روانپزشکی": "psychiatry", "ریه": "pulmonology", "گوش و حلق و بینی": "otorhinolaryngology",
    "مغز و اعصاب": "neurology", "عفونی": "infectious", "پزشک عمومی": "general-practitioner", "روانشناسی": "psychology", "تغذیه": "nutrition",
    "توانبخشی": "rehabilitation", "طب سنتی": "traditional-medicine", "آلرژی": "allergies", "دیابت": "diabetes",
}
DOCTORETO_SLUGS = {"گوارش": "gastroenterologist", "کلیه": "nephrologist", "روماتولوژی": "rheumatologist",
                   "فیزیوتراپی": "physiotherapist"}  # only slugs verified live so far (physiotherapist: Tehran/Shiraz/Mashhad/Karaj/Pardis 25 each, 2026-11-25)
_CITY_SLUGS = {
    "تهران": "tehran", "شیراز": "shiraz", "اصفهان": "isfahan", "مشهد": "mashhad", "کرج": "karaj", "تبریز": "tabriz", "اهواز": "ahvaz",
    "قم": "qom", "کرمانشاه": "kermanshah", "رشت": "rasht", "ارومیه": "urmia", "زاهدان": "zahedan", "کرمان": "kerman", "یزد": "yazd",
    "ساری": "sari", "قزوین": "qazvin", "همدان": "hamedan", "اراک": "arak", "اردبیل": "ardabil", "پردیس": "pardis", "بومهن": "boomehen",
}


@dataclass(frozen=True)
class SiteProvider:
    site: str
    name: str
    specialty: str = ""
    address: str = ""
    city: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    rating: Optional[float] = None  # 0-5
    rating_count: int = 0
    satisfaction_percent: Optional[int] = None
    url: str = ""
    next_free: str = ""
    waiting_time: str = ""
    visits: Optional[int] = None

    @property
    def key(self) -> str:
        return re.sub(r"[\s‌]+", "", f"{self.name}|{self.city}").lower()


@dataclass
class ReadReport:
    providers: list = field(default_factory=list)
    sites: dict = field(default_factory=dict)  # site -> {"ok": bool, "reason": str, "count": int, "seconds": float}
    nearby: list = field(default_factory=list)  # place names the site itself lists as nearby (Doctoreto)


# --- parsing ------------------------------------------------------------------------------------------------------------------------------------
def _next_data(raw: bytes) -> Optional[dict]:
    try:
        html = raw.decode("utf-8", "replace")
        m = _NEXT_DATA.search(html)
        if not m:
            return None
        body = html[m.end():]
        return json.loads(body[: body.index("</script>")])
    except (ValueError, KeyError):
        return None


def _num(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _clean(text: Any, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def _coords(box: Any) -> tuple:
    """(lat, lon) from {lat,lng} / {latitude,longitude} / {lat,lon}; (None, None) when absent or outside Iran."""
    if not isinstance(box, dict):
        return None, None
    lat = _num(box.get("lat", box.get("latitude")))
    lon = _num(box.get("lng", box.get("lon", box.get("longitude"))))
    if lat is None or lon is None or not (24.0 <= lat <= 40.5 and 43.5 <= lon <= 64.0):
        return None, None
    return lat, lon


def parse_paziresh24(raw: bytes) -> list:
    """Providers of a Paziresh24 listing page (``/s/{city}/{expertise}/``); [] when the page is not a listing."""
    data = _next_data(raw)
    out: list = []
    try:
        queries = data["props"]["pageProps"]["dehydratedState"]["queries"]  # type: ignore[index]
        search = next(q["state"]["data"]["search"] for q in queries if isinstance(q.get("state", {}).get("data"), dict) and "search" in q["state"]["data"])
        items = search.get("result") or []
    except (TypeError, KeyError, StopIteration):
        return out
    for it in items:
        if not isinstance(it, dict) or str(it.get("type") or it.get("record_type") or "doctor") != "doctor":
            continue
        core = _clean(it.get("display_name") or it.get("name"), 100)
        if not core:
            continue
        name = _clean(" ".join(x for x in (it.get("prefix"), core) if x), 120)
        centers = [c for c in (it.get("centers") or []) if isinstance(c, dict)]
        center = centers[0] if centers else {}
        lat, lon = _coords(center.get("map") or center.get("location"))
        count = _int(it.get("rates_count"))
        sat = _int(it.get("satisfaction")) if it.get("satisfaction") is not None else None
        star = _num(it.get("star"))
        rating = star if star else (round(sat / 20.0, 2) if sat is not None else None)  # the site's own 0-5 star, else its satisfaction % on a 0-5 scale
        url = str(it.get("url") or "")
        url = ("https://www.paziresh24.com" + url) if url.startswith("/") else url
        out.append(SiteProvider(
            site=SITE_P24, name=name, specialty=_clean(it.get("display_expertise"), 80),
            address=_clean(center.get("address") or it.get("display_address")), city=_clean(center.get("city_name"), 40), lat=lat, lon=lon,
            rating=rating if count else None, rating_count=count, satisfaction_percent=sat if count else None, url=url,
            waiting_time=_clean(it.get("waiting_time"), 40), visits=_int(it.get("number_of_visits")) or None))
    return out


def parse_doctoreto(raw: bytes) -> tuple:
    """(providers, nearby place names) of a Doctoreto listing page (``/doctors/speciality/{slug}/city/{city}``)."""
    data = _next_data(raw)
    providers: list = []
    nearby: list = []
    try:
        queries = data["props"]["pageProps"]["dehydratedState"]["queries"]  # type: ignore[index]
    except (TypeError, KeyError):
        return providers, nearby
    for q in queries:
        key = str(q.get("queryKey"))
        state = (q.get("state") or {}).get("data")
        if key.startswith("['doctors', 'list'") and isinstance(state, dict):
            for it in state.get("data") or []:
                if not isinstance(it, dict) or not it.get("fullName"):
                    continue
                place = (it.get("places") or [{}])[0] if isinstance(it.get("places"), list) and it.get("places") else {}
                coords = place.get("coordinates") if isinstance(place, dict) else None
                lat, lon = _coords({"lat": (coords or {}).get("latitude"), "lon": (coords or {}).get("longitude")}) if isinstance(coords, dict) else (None, None)
                rate = it.get("rate") if isinstance(it.get("rate"), dict) else {}
                count = _int(rate.get("count"))
                avg = _num(rate.get("rateAverage"))
                nxt = ((it.get("nextFreeTimes") or {}).get("general") or {}) if isinstance(it.get("nextFreeTimes"), dict) else {}
                route = str(it.get("profileRoute") or "")
                providers.append(SiteProvider(
                    site=SITE_DOCTORETO, name=_clean(it.get("fullName"), 120), specialty=_clean(it.get("specialityLabel"), 80),
                    address=_clean((place or {}).get("address")), city=_clean(((place or {}).get("city") or {}).get("name"), 40), lat=lat, lon=lon,
                    rating=avg if (count and avg is not None) else None, rating_count=count,
                    satisfaction_percent=_int(rate.get("percent")) if (count and rate.get("percent") is not None) else None,
                    url=("https://doctoreto.com" + route) if route.startswith("/") else route, next_free=_clean(nxt.get("fullTextDisplay"), 60)))
        elif key.startswith("['doctors', 'nearbyNeighborhood'") and isinstance(state, dict):
            for group in ("nearbyCities", "nearbyNeighborhoods"):
                for item in (state.get(group) or [])[:12]:
                    name = _clean(item.get("name") if isinstance(item, dict) else item, 40)
                    if name:
                        nearby.append(name)
    return providers, nearby


# --- URLs ---------------------------------------------------------------------------------------------------------------------------------------
def city_slug(city: Optional[str]) -> Optional[str]:
    return _CITY_SLUGS.get(re.sub(r"\s+", " ", (city or "").strip()))


def listing_urls(specialty: Optional[str], city: Optional[str], page: int = 1) -> list:
    """[(site, url)] listing pages for (canonical specialty, city); only sites whose slugs are known for BOTH the specialty and the city.
    ``page`` > 1 is the site's own ``?page=N`` (both sites paginate, checked live 2026-11-25)."""
    slug = city_slug(city)
    out: list = []
    if not slug:
        return out
    suffix = f"?page={int(page)}" if int(page) > 1 else ""
    if specialty in P24_SLUGS:
        out.append((SITE_P24, f"https://www.paziresh24.com/s/{slug}/{P24_SLUGS[specialty]}/{suffix}"))
    if specialty in DOCTORETO_SLUGS:
        out.append((SITE_DOCTORETO, f"https://doctoreto.com/doctors/speciality/{DOCTORETO_SLUGS[specialty]}/city/{slug}{suffix}"))
    return out


# --- ranking ------------------------------------------------------------------------------------------------------------------------------------
def haversine_km(a: tuple, b: tuple) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def trust_score(p: SiteProvider) -> float:
    """0-5: the patients' average shrunk toward the prior by how few reviews back it (no reviews = the prior, never a perfect score)."""
    avg = p.rating if p.rating is not None else RATING_PRIOR
    n = p.rating_count if p.rating is not None else 0
    return (avg * n + RATING_PRIOR * RATING_PRIOR_WEIGHT) / (n + RATING_PRIOR_WEIGHT)


def rank(providers: Sequence[SiteProvider], *, origin: Optional[tuple] = None, exclude: Sequence[str] = ()) -> list:
    """Most credible first: the shrunk rating dominates, the distance from ``origin`` (lat, lon) breaks near-ties and lifts what is close, and the
    same doctor seen on two sites is one entry (the one with more reviews). ``exclude`` = keys already introduced (the next-five flow)."""
    skip = set(exclude)
    best: dict = {}
    for p in providers:
        if p.key in skip:
            continue
        cur = best.get(p.key)
        if cur is None or p.rating_count > cur.rating_count:
            best[p.key] = p

    def score(p: SiteProvider) -> float:
        s = trust_score(p)
        if origin and p.lat is not None and p.lon is not None:
            s -= min(haversine_km(origin, (p.lat, p.lon)), 60.0) / 60.0 * 0.8  # up to -0.8 star for being 60 km away
        return s

    return sorted(best.values(), key=lambda p: (-score(p), -p.rating_count, p.name))


def page(ranked: Sequence[SiteProvider], number: int = 1) -> list:
    """Page ``number`` (1-based) of FIVE."""
    start = (max(1, number) - 1) * PAGE_SIZE
    return list(ranked[start:start + PAGE_SIZE])


# --- reading ------------------------------------------------------------------------------------------------------------------------------------
_cache: dict = {}
_lock = threading.Lock()
_pace_lock = threading.Lock()
_last_live_fetch = [0.0]


def readers_enabled() -> bool:
    return (os.getenv(ENABLED_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def _pace_live_fetch(deadline: Optional[float] = None) -> bool:
    """At least ``MIN_GAP_SECONDS`` between two LIVE page requests of this process (cache hits never wait). False = the caller's deadline would
    pass before this request could start: it is skipped, so work whose caller already gave up never uses a pacing slot (Codex P2, PR 220)."""
    with _pace_lock:
        now = time.time()
        wait = _last_live_fetch[0] + MIN_GAP_SECONDS - now
        if deadline is not None and now + max(wait, 0.0) >= deadline:
            return False
        if wait > 0:
            time.sleep(wait)
        _last_live_fetch[0] = time.time()
        return True


def _read_one(site: str, url: str, fetch: Callable[[str], Any], deadline: Optional[float] = None) -> tuple:
    started = time.time()
    with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < CACHE_TTL_SECONDS:
            return site, hit[1], hit[2], {"ok": True, "reason": "cache", "count": len(hit[1]), "seconds": 0.0}
    try:
        if not _pace_live_fetch(deadline):
            return site, [], [], {"ok": False, "reason": "deadline", "count": 0, "seconds": round(time.time() - started, 2)}
        fr = fetch(url)
        if not getattr(fr, "ok", False):
            return site, [], [], {"ok": False, "reason": getattr(fr, "reason", "") or "unreadable", "count": 0, "seconds": round(time.time() - started, 2)}
        if site == SITE_DOCTORETO:
            items, nearby = parse_doctoreto(fr.body)
        else:
            items, nearby = parse_paziresh24(fr.body), []
        if items or nearby:  # an empty page may be a temporary/challenge page: never cache it, so the next read retries (Codex P2, PR 218)
            with _lock:
                if len(_cache) > 128:
                    _cache.pop(next(iter(_cache)))
                _cache[url] = (time.time(), items, nearby)
        return site, items, nearby, {"ok": True, "reason": "", "count": len(items), "seconds": round(time.time() - started, 2)}
    except Exception as exc:  # noqa: BLE001 - one site down never breaks the answer
        logger.info("site_reader_failed site=%s reason=%s", site, type(exc).__name__)
        return site, [], [], {"ok": False, "reason": type(exc).__name__, "count": 0, "seconds": round(time.time() - started, 2)}


def read_sites(specialty: Optional[str], city: Optional[str], *, fetch: Optional[Callable[[str], Any]] = None, page: int = 1) -> ReadReport:
    """Read the listing pages (page ``page``) of every known site for (canonical specialty, city) IN PARALLEL within one time budget."""
    report = ReadReport()
    urls = listing_urls(specialty, city, page)
    if not urls:
        return report
    fetcher = fetch or safe_fetch.fetch_page
    pool = ThreadPoolExecutor(max_workers=len(urls))
    try:
        deadline = time.time() + READ_TIMEOUT_SECONDS
        futures = [pool.submit(_read_one, site, url, fetcher, deadline) for site, url in urls]
        for (site, _url), fut in zip(urls, futures):
            try:
                _s, items, nearby, status = fut.result(timeout=max(0.1, deadline - time.time()))
            except Exception:  # noqa: BLE001
                items, nearby, status = [], [], {"ok": False, "reason": "timeout", "count": 0, "seconds": READ_TIMEOUT_SECONDS}
            report.providers.extend(items)
            report.nearby.extend(n for n in nearby if n not in report.nearby)
            report.sites[site] = status
    finally:
        pool.shutdown(wait=False)
    return report


def _squash(text: Any) -> str:
    return re.sub(r"[\s‌‎‏\-_.,،]+", "", str(text or "")).lower()


def _area_first(ranked: Sequence[SiteProvider], area: Optional[str]) -> list:
    """Providers whose address names the user's neighbourhood come first (the credibility order is kept inside each group)."""
    key = _squash(area)
    if not key:
        return list(ranked)
    near = [p for p in ranked if key in _squash(p.address)]
    return near + [p for p in ranked if p not in near]


_PROFILE_PATHS = {SITE_P24: re.compile(r"^/(?:dr|doctor)/[^/?#]+/?"), SITE_DOCTORETO: re.compile(r"^/doctor/[^/?#]+")}


def encode_url(url: str) -> str:
    """The profile URL with its path percent-encoded (the live pages carry raw Persian slugs, «/dr/دکتر-الف/»): every browser, launcher and page
    reader opens the encoded form (checked on the live pages 2026-11-25: the raw form fails in the server's page reader)."""
    try:
        parsed = urlparse(url or "")
        return f"{parsed.scheme}://{parsed.netloc}{quote(parsed.path, safe='/-._~%')}" + (f"?{parsed.query}" if parsed.query else "")
    except ValueError:
        return url


def profile_url_ok(url: str) -> bool:
    """The link is the PAGE OF ONE DOCTOR on its own site (not a listing, not another host): https, the site's host, and the site's profile path."""
    try:
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower().removeprefix("www.")
        rx = _PROFILE_PATHS.get(host)
        return parsed.scheme == "https" and bool(rx) and bool(rx.match(parsed.path or "")) and not parsed.username
    except ValueError:
        return False


def _wrong_specialty(specialty: Optional[str], p: SiteProvider) -> bool:
    """True when the provider's OWN text explicitly names other specialties and not the requested one (a listing can carry a neighbouring
    specialty). The first text that names any specialty decides, like ``specialty_lexicon.result_matches_specialty``. ACCURACY (Javad 2026-11-25):
    a provider whose own text names NO specialty (a degree, a fellowship, a midwife - the Mashhad gynaecology listing was 14 of 20 midwives) is
    NOT introduced as that specialist. A label the lexicon does not know never filters. Never raises."""
    try:
        from backend.app.services.i5 import specialty_lexicon as lexicon

        for text in (p.specialty, p.name):
            names = lexicon.named_specialties(re.sub(r"[،,.;:/|()\-–]+", " ", str(text or "")))
            if names:
                return specialty not in names
        return bool(lexicon.is_known(specialty))
    except Exception:  # noqa: BLE001
        return False


def _wrong_city(city: Optional[str], p: SiteProvider) -> bool:
    """True when the provider's selected clinic names ANOTHER city than the one asked (the parsers take the provider's first clinic; a doctor with
    clinics in two cities can come up on a listing of the other). A provider with no city text is kept - the listing page is for that city."""
    want, have = _squash(city), _squash(p.city)
    return bool(want and have and want not in have and have not in want)


_verified: dict = {}  # profile url -> (checked at, "ok" | "bad")


def _fa_fold(text: Any) -> str:
    """Letters comparable across sites: Arabic Yeh/Kaf folded, the «دکتر» prefix, spaces, half-spaces and punctuation removed."""
    t = str(text or "").replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u0649", "\u06cc")
    t = re.sub(r"[\u064b-\u0652\u0640]", "", t)
    t = re.sub(r"^\s*(?:\u062f\u06a9\u062a\u0631|\u062f\u06a9\u062a\u0631\u0627)\s+", "", t)
    return re.sub(r"[\s\u200c\u200e\u200f\-_.,\u060c:;()]+", "", t).lower()


def verify_enabled() -> bool:
    return (os.getenv(VERIFY_ENV) or "true").strip().lower() not in {"0", "false", "no", "off"}


def verify_profile(p: SiteProvider, fetch: Optional[Callable[[str], Any]] = None, deadline: Optional[float] = None) -> str:
    """Does the doctor's own page open and show that doctor? ``ok`` / ``bad`` (cached 24 h) or ``unknown`` (blocked, timed out, no time left: NOT cached,
    and the doctor is then shown unchecked - the check never makes the chat worse than not checking). ``bad`` = the page is gone (404/410) or it does
    not carry the listed name."""
    url = encode_url(p.url)
    now = time.time()
    with _lock:
        hit = _verified.get(url)
        if hit and now - hit[0] < VERIFY_TTL_SECONDS:
            return hit[1]
    try:
        if not _pace_live_fetch(deadline):
            return "unknown"
        fr = (fetch or safe_fetch.fetch_page)(url)
        if not getattr(fr, "ok", False):
            status = "bad" if str(getattr(fr, "reason", "")) in {"http_404", "http_410"} else "unknown"
        else:
            body = getattr(fr, "body", b"") or b""
            page_text = _fa_fold(body.decode("utf-8", "ignore") if isinstance(body, (bytes, bytearray)) else str(body))
            tokens = [t for t in (_fa_fold(w) for w in re.split(r"\s+", str(p.name or "").strip())) if len(t) >= 2 and t != _fa_fold("\u062f\u06a9\u062a\u0631")]
            status = "ok" if tokens and all(t in page_text for t in tokens) else "bad"
    except Exception:  # noqa: BLE001
        return "unknown"
    if status in ("ok", "bad"):
        with _lock:
            if len(_verified) > 512:
                _verified.pop(next(iter(_verified)))
            _verified[url] = (time.time(), status)
    return status


def _qualified(providers: Sequence[SiteProvider], specialty: Optional[str], city: Optional[str]) -> list:
    """The specialty, city and link checks come BEFORE ranking and paging, so a wrong or unusable entry never takes one of the five places."""
    return [p for p in providers if p.name and profile_url_ok(p.url) and not _wrong_specialty(specialty, p) and not _wrong_city(city, p)]


def provider_rows(specialty: Optional[str], city: Optional[str], *, area: Optional[str] = None, number: int = 1, exclude: Sequence[str] = (),
                  origin: Optional[tuple] = None, fetch: Optional[Callable[[str], Any]] = None) -> list:
    """Page ``number`` (FIVE) of the most credible providers for (canonical specialty, city), as the SAME row dicts the web lookup returns, so the
    chat's identities, links and wording need no second path. Every row is a page of a known listing site (``trusted``), carries the patients'
    rating and count the site published, and is transient (nothing is stored). Up to ``MAX_PAGES`` listing pages are read while fewer than five
    (plus spares) qualify; each shown doctor's PROFILE PAGE is checked (opens, carries the listed name; result kept 24 h). Fail-open: any problem
    = an empty list."""
    try:
        if not listing_urls(specialty, city):
            return []
        started = time.time()
        providers: list = []
        ranked: list = []
        for pg in range(1, MAX_PAGES + 1):
            if pg > 1 and time.time() - started > READ_TOTAL_SECONDS:
                break
            report = read_sites(specialty, city, fetch=fetch, page=pg)
            if not any(v.get("ok") and v.get("count") for v in report.sites.values()):
                break  # nothing (more) to read on this page
            providers.extend(report.providers)
            ranked = _area_first(rank(_qualified(providers, specialty, city), origin=origin, exclude=exclude), area)
            if len(ranked) >= (max(1, number) - 1) * PAGE_SIZE + PAGE_SIZE + SPARE:
                break
        today = date.today().isoformat()
        chosen: list = []
        checking = verify_enabled()
        deadline = time.time() + VERIFY_BUDGET_SECONDS
        for p in ranked[(max(1, number) - 1) * PAGE_SIZE:]:
            if len(chosen) >= PAGE_SIZE:
                break
            status = verify_profile(p, fetch, deadline) if checking and time.time() < deadline else "unknown"
            if status != "bad":
                chosen.append((p, status))
        rows = []
        for p, status in chosen:
            rows.append({"name": p.name, "specialty": p.specialty or specialty, "city": p.city or city, "address": p.address or None, "phone": None,
                         "source_url": encode_url(p.url), "trusted": True, "visit_days": [], "next_turn": p.next_free or None,
                         "rating_avg": p.rating, "rating_count": p.rating_count or None, "phone_status": None, "checked_on": today,
                         "page_read": True, "why": (), "_key": p.key, "link_checked": status == "ok"})
        return rows
    except Exception:  # noqa: BLE001 - the chat must never break because a site could not be read
        logger.info("site_reader_rows_failed")
        return []
