"""R-074 step 7 (D-208): open-web lookup of PUBLIC FACTS (price, opening hours, availability, provider intro).

Decision D-208 (Javad): no closed domain list; sources are graded instead. Tier 1 = official / well-known reference
(`directory_web_lookup.is_trusted_url`), tier 2 = a credible business page (pharmacy chain, clinic, gym, shop, booking
platform). Every fact is shown with its site, an approximate-marker and the date; when nothing credible is found Sedi says so.

Guards (independent of any list):
1. only public facts - a question must carry a price / hours / availability / provider cue;
2. health / medical KNOWLEDGE never comes from the open web (dose, side effects, symptoms, treatment ... = no lookup);
3. emergencies are I4's (any emergency cue = no lookup);
4. privacy: the outbound query is a short generic topic only - a question with first-person words, digits, e-mail or
   phone fragments, or more than six topic words is NOT searched (fail-closed);
5. hosts: search engines / social posts without a profile are rejected (same blocked hosts as the directory lookup);
6. flag SEDI_PUBLIC_WEB_LOOKUP_ENABLED (default OFF), daily cap, 24 h in-memory cache, fail-open, nothing is stored.

Reuses the transient-lookup plumbing of ``directory_web_lookup`` (R-005: no second web stack).
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

from backend.app.services.i5.directory_web_lookup import _usable_url, is_trusted_url

FLAG = "SEDI_PUBLIC_WEB_LOOKUP_ENABLED"
MODEL_ENV = "SEDI_PUBLIC_WEB_LOOKUP_MODEL"
DAILY_CAP_ENV = "SEDI_PUBLIC_WEB_LOOKUP_DAILY_CAP"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_DAILY_CAP = 100
CACHE_TTL_SECONDS = 24 * 3600
_CACHE_MAX = 256
MAX_RESULTS = 5
MAX_TOPIC_WORDS = 6

_lock = threading.Lock()
_usage: dict[str, int] = {}
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

_ARABIC_MARKS = re.compile("[ً-ٰٟـ‌‏‎]")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(text: str) -> str:
    s = str(text or "").translate(_DIGITS).lower()
    s = s.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    s = _ARABIC_MARKS.sub("", s)
    return " ".join(re.sub(r"[?؟!.,،:;«»\"'()\[\]]", " ", s).split())


# --- what is a public-fact question -------------------------------------------------------------------------------
_KINDS: dict[str, re.Pattern] = {
    "price": re.compile(
        r"(قیمت|هزینه|تعرفه|چنده|چند تومان|چقدر (?:می ?شود|میشه|پول|هزینه)|price|cost of|how much|prices|سعر|تکلفه|بكم|بکم)"
    ),
    "hours": re.compile(
        r"(ساعت کار|ساعات کار|ساعت کاری|تا چه ساعتی|چه ساعتی باز|باز است تا|opening hours|open until|what time does|"
        r"what time is .* open|working hours|مواعید العمل|ساعات العمل|متی یفتح|متی تفتح)"
    ),
    "availability": re.compile(
        r"(کجا.{0,30}(?:بخرم|خرید|پیدا کنم|تهیه)|موجود است|موجوده|where (?:can|to) (?:i )?(?:buy|find|get)|"
        r"available (?:at|in)|in stock|اين اجد|این اجد|اين اشتري|این اشتری|متوفر)"
    ),
    "provider": re.compile(
        r"(?:(?:معرفی|پیشنهاد|بهترین|نزدیک ?ترین|recommend|best|nearest|near me|اقرب|افضل).{0,20}"
        r"(?:باشگاه|استخر|داروخانه|فروشگاه|سالن|gym|pool|pharmacy|store|shop|صیدلیه|نادی))|"
        r"(?:(?:باشگاه|استخر|داروخانه|فروشگاه|gym|pool|pharmacy|store|shop|صیدلیه|نادی).{0,20}"
        r"(?:معرفی|پیشنهاد|بهترین|نزدیک|recommend|best|nearest|اقرب|افضل))"
    ),
}
# Health KNOWLEDGE questions (never answered from the open web) and emergencies (I4).
_MEDICAL_ADVICE = re.compile(
    r"(دوز|دوزاژ|عوارض|علائم|نشانه ?های|درمان|تشخیص|تداخل|مصرف (?:کنم|کنیم|شود)|چطور مصرف|چگونه مصرف|"
    r"dose|dosage|side effect|symptom|treat|diagnos|interaction|contraindic|"
    r"جرعه|اعراض|علاج|تشخیص|اثار جانبیه|هل یجوز)"
)
_EMERGENCY = re.compile(
    r"(خودکشی|خودم را بکشم|سکته|درد قفسه|تنگی نفس|مسمومیت|اورژانس|suicide|kill myself|heart attack|chest pain|"
    r"can.?t breathe|overdose|emergency|انتحار|نوبه قلبیه|طوارئ)"
)
# Personal / identifying cues: such a question is not searched at all (the topic could carry private details).
_PERSONAL = re.compile(
    r"(?:(?<!\S)(?:من|مرا|خودم|دارم|داریم|بیمارم|مبتلا|مادرم|پدرم|همسرم|فرزندم|پسرم|دخترم|my|mine|myself|"
    r"i have|i am|i m|i take|i feel|have|has|diagnosed|عندی|لی|امی|ابی|أنا|انا)(?!\S))|@|https?:|www\."
)

_FILLER = frozenset(
    "قیمت هزینه تعرفه چنده چند تومان تومان چقدر می شود میشود میشه میتوان میتونم میتوانم است هست را رو در از به با برای یک بهترین معرفی پیشنهاد نزدیک ترین "
    "ساعت کار کاری ساعات تا چه ساعتی باز موجود موجوده کجا بخرم خرید پیدا کنم تهیه می توان میتوان میتونم می تونم و یا هم هر "
    "the a an of is are how much does do what where can to buy find get price cost prices for in at on and or "
    "opening hours working open until time available stock best nearest recommend near "
    "سعر تکلفه بکم متی یفتح تفتح اين این اجد اشتری متوفر اقرب افضل في من على الى".split()
)
_KIND_WORD = {
    "price": {"fa": "قیمت", "ar": "سعر", "en": "price"},
    "hours": {"fa": "ساعت کاری", "ar": "ساعات العمل", "en": "opening hours"},
    "availability": {"fa": "محل خرید", "ar": "مكان الشراء", "en": "where to buy"},
    "provider": {"fa": "معرفی", "ar": "افضل", "en": "best"},
}


@dataclass(frozen=True)
class FactRequest:
    kind: str
    topic: str
    query: str
    language: str


def lookup_enabled() -> bool:
    return os.getenv(FLAG, "").strip().lower() in {"1", "true", "yes", "on"}


def _lang_of(language: Optional[str], text: str) -> str:
    lang = (language or "").lower()[:2]
    if lang in {"fa", "ar", "en"}:
        return lang
    return "fa" if re.search(r"[؀-ۿ]", text) else "en"


def classify_public_fact(text: str, language: Optional[str] = None) -> Optional[FactRequest]:
    """A clear public-fact question with a short, generic, non-personal topic, else None (fail-closed)."""
    raw = str(text or "")
    if not raw.strip() or len(raw) > 300:
        return None
    s = _norm(raw)
    if _EMERGENCY.search(s) or _MEDICAL_ADVICE.search(s) or _PERSONAL.search(s):
        return None
    kind = next((k for k, pat in _KINDS.items() if pat.search(s)), None)
    if not kind:
        return None
    if re.search(r"\d", s):  # digits could be a phone, an id or a personal figure
        return None
    words = [w for w in s.split() if w not in _FILLER and len(w) >= 2]
    if not words or len(words) > MAX_TOPIC_WORDS:
        return None
    lang = _lang_of(language, raw)
    topic = " ".join(words)
    query = f"{_KIND_WORD[kind][lang]} {topic}" if kind != "provider" else f"{topic} {_KIND_WORD[kind][lang]}"
    return FactRequest(kind=kind, topic=topic, query=query[:120], language=lang)


# --- web call + validation ----------------------------------------------------------------------------------------
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
                "required": ["title", "fact", "observed_date", "source_url"],
                "properties": {
                    "title": {"type": "string"},
                    "fact": {"type": "string"},
                    "observed_date": {"type": "string"},
                    "source_url": {"type": "string"},
                },
            },
        }
    },
}

_INSTRUCTIONS = (
    "Search the web for the PUBLIC FACT asked in the query (price, opening hours, availability, or a provider). "
    "Return only facts shown on the source page, copied exactly as shown (keep the currency and unit); "
    "observed_date is the date shown on the page, or an empty string. source_url must be the exact page. "
    "Prefer official sites and credible business pages (chain pharmacies, clinics, gyms, shops, booking platforms). "
    "Never give medical advice, never invent a price, hour or address; return an empty list when no credible page exists. "
    "Return at most 5 results."
)


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


def _call_web_search(query: str, client: Any = None) -> list[dict[str, Any]]:
    if client is None:
        from openai import OpenAI

        client = OpenAI()
    resp = client.responses.create(
        model=os.getenv(MODEL_ENV, DEFAULT_MODEL),
        tools=[{"type": "web_search"}],
        instructions=_INSTRUCTIONS,
        input=query,
        text={"format": {"type": "json_schema", "name": "public_facts", "schema": _SCHEMA, "strict": True}},
    )
    data = json.loads(getattr(resp, "output_text", "") or "{}")
    return [r for r in (data.get("results") or []) if isinstance(r, dict)]


def validate_results(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """A real page link, a non-empty fact, no search-engine / social host; tier 1 (known/official) ranked first."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items:
        url = str(it.get("source_url") or "").strip()
        fact = " ".join(str(it.get("fact") or "").split())[:300]
        title = " ".join(str(it.get("title") or "").split())[:120]
        if not fact or not _usable_url(url):
            continue
        key = url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "fact": fact,
                "observed_date": " ".join(str(it.get("observed_date") or "").split())[:40],
                "source_url": url,
                "tier": 1 if is_trusted_url(url, "IR") else 2,
            }
        )
    out.sort(key=lambda r: r["tier"])  # stable: tier 1 first
    return out[:MAX_RESULTS]


def search_public_facts(req: FactRequest, client: Any = None) -> Optional[list[dict[str, Any]]]:
    """One guarded search. None = not attempted (flag off / cap / error); [] = attempted, nothing credible."""
    if not lookup_enabled():
        return None
    now = time.time()
    with _lock:
        hit = _cache.get(req.query)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return [dict(r) for r in hit[1]]
    if not _take_quota():
        return None
    try:
        results = validate_results(_call_web_search(req.query, client))
    except Exception:  # noqa: BLE001 - optional enrichment; the chat must never break
        return None
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
        _cache[req.query] = (now, [dict(r) for r in results])
    return results


# --- the block handed to the chat model ---------------------------------------------------------------------------
_RULES = (
    "PUBLIC WEB FACTS (transient, not stored, not medical knowledge). Use ONLY these lines for the public fact asked. "
    "State each fact with its site name, say it is approximate when it is a price, and give the date when shown. "
    "Tier 1 = official/known source, tier 2 = business page. If two sources disagree, give a range. "
    "Never use them for medical advice; the governed knowledge and the safety rules stay in force."
)
_NONE = (
    "PUBLIC WEB FACTS: a web search was done for this question and no credible source was found. "
    "Say honestly that you could not find a reliable source; do not guess a price, hour or address."
)


def format_block(req: FactRequest, results: Sequence[dict[str, Any]]) -> str:
    if not results:
        return _NONE
    lines = [f"- [tier {r['tier']}] {r['title']}: {r['fact']} (site: {r['source_url']}; date: {r['observed_date'] or 'not shown'})" for r in results]
    return _RULES + f"\nQuestion kind: {req.kind}; topic: {req.topic}\n" + "\n".join(lines)


def public_facts_block(user_message: str, language: Optional[str] = None, client: Any = None) -> Optional[str]:
    """Chat hook: None unless the flag is on AND the message is a safe public-fact question AND a search was done."""
    try:
        if not lookup_enabled():
            return None
        req = classify_public_fact(user_message, language)
        if req is None:
            return None
        results = search_public_facts(req, client)
        if results is None:
            return None
        return format_block(req, results)
    except Exception:  # noqa: BLE001 - fail-open
        return None
