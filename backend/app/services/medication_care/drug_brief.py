"""R-088 amendment 3 / R-091 (D-384), package A2: Sedi introduces the medicine the user names, from the web.

Javad (2026-11-18): Sedi may search ONLINE to identify and introduce a medicine; the correct name is critical.

Guards (this is NOT the open-web public-facts lookup, whose guard 2 still forbids medical knowledge for everything else):
1. the outbound query is the medicine NAME only - no user, health detail, phone or e-mail ever leaves (``clean_name``);
2. the answer is a strict JSON object; what reaches the user is ONE plain sentence (what it is / what it is usually used for),
   scrubbed of links, numbers with units, dose words and anything but letters and punctuation - web text is untrusted data;
3. «recognized» must be true, otherwise Sedi asks for the exact name / a photo of the box (never guesses);
4. the two-source rule (R-082): the uses are stated plainly only when two DIFFERENT sites support them; one site -> the wording
   says «according to <site>»; each answer shows the sites and the date;
5. never a dose, never start / stop / change advice, no side-effect lists (R-014); the care conversation follows;
6. kill switch (code default ON, no env change) SEDI_DRUG_WEB_LOOKUP_DISABLED, daily cap, 24 h cache, fail-open: no result ->
   the interview simply continues without the introduction.

Reuses the transient web-search plumbing of ``directory_web_lookup`` (R-005: no second web stack).
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Sequence

from backend.app import sedi_copy
from backend.app.services.i5.directory_web_lookup import _host, _usable_url

DISABLED_ENV = "SEDI_DRUG_WEB_LOOKUP_DISABLED"
MODEL_ENV = "SEDI_DRUG_WEB_LOOKUP_MODEL"
DAILY_CAP_ENV = "SEDI_DRUG_WEB_LOOKUP_DAILY_CAP"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_DAILY_CAP = 100
CACHE_TTL_SECONDS = 24 * 3600
_CACHE_MAX = 256
MAX_SOURCES = 3

# Well-known drug-information authorities (ranked first); official / university suffixes are trusted as well.
TRUSTED_DOMAINS = (
    "medlineplus.gov", "dailymed.nlm.nih.gov", "nhs.uk", "mayoclinic.org", "drugs.com", "who.int", "fda.gov",
    "ema.europa.eu", "webmd.com", "fda.gov.ir", "pubchem.ncbi.nlm.nih.gov",
)
TRUSTED_SUFFIXES = (".gov", ".gov.ir", ".edu", ".ac.ir", ".nhs.uk")

_lock = threading.Lock()
_usage: dict[str, int] = {}
_cache: dict[str, tuple[float, "DrugBrief"]] = {}


@dataclass(frozen=True)
class DrugBrief:
    recognized: bool
    summary: str = ""
    generic_name: str = ""
    hosts: tuple[str, ...] = field(default_factory=tuple)
    two_source: bool = False
    on_date: str = ""


def enabled() -> bool:
    return os.getenv(DISABLED_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}


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


_NAME_OK = re.compile(r"^[^\W_][\w‌\- ]{1,58}$", re.UNICODE)


def clean_name(name: Optional[str]) -> Optional[str]:
    """The only text that may leave: a short medicine name. None = refuse to search (privacy, fail-closed)."""
    text = " ".join((name or "").replace("‌", " ").split())
    if not text or "@" in text or "://" in text or re.search(r"\d{6,}", text) or len(text.split()) > 5:
        return None
    return text if _NAME_OK.match(text) else None


def _is_trusted(url: str) -> bool:
    host = _host(url)
    return bool(host) and (any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS) or host.endswith(TRUSTED_SUFFIXES))


_BAD_SUMMARY = re.compile(
    r"(https?://|www\.|\d+\s*(?:mg|mcg|µg|ml|iu|g\b|میلی|میکرو|واحد|قرص\s+در)|\bdos(?:e|age)\b|\bmg\b|دوز|جرعه|\bجرعة\b)",
    re.I,
)
_ALLOWED_CHARS = re.compile(r"^[\w\s‌،؛؟«»ؐ-ًؚ-ٰٟ\-.,;:()/'’\"]+$", re.UNICODE)


def clean_summary(text: Any) -> Optional[str]:
    """One plain sentence as inert data: no links, no numbers with units, no dose words, bounded."""
    s = " ".join(re.sub(r"[\u0000-\u001f\u007f]", " ", str(text or "")).split())
    if not 15 <= len(s) <= 260 or _BAD_SUMMARY.search(s) or not _ALLOWED_CHARS.match(s):
        return None
    return s


_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["recognized", "generic_name", "summary", "sources"],
    "properties": {
        "recognized": {"type": "boolean"},
        "generic_name": {"type": "string"},
        "summary": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "url"],
                "properties": {"title": {"type": "string"}, "url": {"type": "string"}},
            },
        },
    },
}


def _instructions(language: str) -> str:
    lang = {"fa": "Persian", "ar": "Arabic", "en": "English"}.get(language, "English")
    return (
        "Identify the medicine named in the query (it may be a Persian, Arabic or English brand or generic name, possibly with "
        "a spelling variant) using reliable drug-information websites (official regulators, MedlinePlus, DailyMed, NHS, "
        "Mayo Clinic, Drugs.com, Iranian FDA). Set recognized=false when you are not sure which single medicine it is. "
        f"summary: ONE plain sentence in {lang} saying what it is and what it is usually used for; no dose, no numbers with "
        "units, no side effects, no advice, no links. sources: the exact pages you used (at least two different sites when "
        "available). Never invent a medicine or a source."
    )


def _call_web_search(name: str, language: str, client: Any = None) -> dict[str, Any]:
    if client is None:
        from openai import OpenAI

        client = OpenAI()
    resp = client.responses.create(
        model=os.getenv(MODEL_ENV, DEFAULT_MODEL),
        tools=[{"type": "web_search"}],
        instructions=_instructions(language),
        input=name,  # the name ONLY (guard 1)
        text={"format": {"type": "json_schema", "name": "drug_brief", "schema": _SCHEMA, "strict": True}},
    )
    data = json.loads(getattr(resp, "output_text", "") or "{}")
    return data if isinstance(data, dict) else {}


def validate(data: dict[str, Any], today: Optional[str] = None) -> Optional[DrugBrief]:
    """None = unusable answer (treated like «not attempted»); recognized=False = Sedi must ask for the exact name."""
    if not data.get("recognized"):
        return DrugBrief(recognized=False)
    summary = clean_summary(data.get("summary"))
    if summary is None:
        return None
    urls = [str(s.get("url") or "").strip() for s in (data.get("sources") or []) if isinstance(s, dict)]
    urls = [u for u in urls if _usable_url(u)]
    hosts: list[str] = []
    for u in sorted(urls, key=lambda x: not _is_trusted(x)):  # stable: authorities first
        h = _host(u)
        if h and h not in hosts:
            hosts.append(h)
    if not hosts:  # no real source -> never state it as fact
        return None
    generic = " ".join(str(data.get("generic_name") or "").split())[:60]
    return DrugBrief(
        recognized=True,
        summary=summary,
        generic_name=generic,
        hosts=tuple(hosts[:MAX_SOURCES]),
        two_source=len(hosts) >= 2,
        on_date=today or date.today().isoformat(),
    )


def lookup(name: str, language: str, client: Any = None) -> Optional[DrugBrief]:
    """One guarded search. None = not attempted / failed (flag, cap, privacy, error); the interview then simply goes on."""
    if not enabled():
        return None
    q = clean_name(name)
    if not q:
        return None
    key = f"{q.lower()}|{language}"
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    if not _take_quota():
        return None
    try:
        brief = validate(_call_web_search(q, language, client))
    except Exception:  # noqa: BLE001 - optional enrichment; the chat must never break
        return None
    if brief is None:
        return None
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (now, brief)
    return brief


def compose(brief: DrugBrief, name: str, language: str) -> str:
    """The introduction sentence: what the medicine is used for + the sites + the date (two sources -> stated plainly)."""
    lang = language if language in ("fa", "ar", "en") else "en"
    key = "medication.chat.brief.line" if brief.two_source else "medication.chat.brief.single"
    return sedi_copy.t(key, lang, name=name, summary=brief.summary, sources=", ".join(brief.hosts), date=brief.on_date)
