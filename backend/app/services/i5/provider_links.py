"""R-107 am.3 (Javad 2026-11-21): the links of a doctor introduction live OUTSIDE the chat bubble.

«لینک‌های معرفی پزشک خارج از کادر چت و با خط آبی و قابل باز شدن و وارد شدن به سایت اصلی باشد».

The text bubble tells the doctor (name, specialty, address, phone, days, rating); the page of that doctor on the ORIGINAL site (Paziresh24,
Doctor-Doctor, Doctoreto, Nobat ... - the page the data came from) is a LINK the app shows as a blue underlined line below the bubble and
opens in the browser. This module is the ONE place that turns a directory result into those links and (for an app that says it can show
them) removes the raw URLs from the bubble text.

Safety (R-089 / R-107 / R-114): a link is built ONLY from a verified directory/web result's own ``source_url`` or from the directory's own
search-page patterns - never from model text; https only, no credentials, no javascript/data schemes, deduplicated, at most five.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import urlparse

MAX_LINKS = 6  # five near doctors + at most one «worth the trip» (R-120 am.2)
LABEL_MAX = 120  # «دکتر الف — متخصص پوست — پذیرش۲۴»: name + specialty + site
KIND_PROVIDER = "provider"  # the page of one doctor / clinic / lab on the original site
KIND_SEARCH = "search"  # a search page on a booking site (nothing verified was found)

_SITE_NAMES = {
    "paziresh24.com": {"fa": "پذیرش۲۴", "ar": "Paziresh24", "en": "Paziresh24"},
    "drdr.ir": {"fa": "دکتر دکتر", "ar": "Doctor-Doctor", "en": "Doctor-Doctor"},
    "doctoreto.com": {"fa": "دکترتو", "ar": "Doctoreto", "en": "Doctoreto"},
    "nobat.ir": {"fa": "نوبت", "ar": "Nobat", "en": "Nobat"},
    "irimc.org": {"fa": "نظام پزشکی", "ar": "IRIMC", "en": "Medical Council"},
}
_URL = re.compile(r"https?://[^\s<>«»\"']+", re.I)
_SOURCE_LEAD = re.compile(r"[؛;،,]?\s*(?:منبع|المصدر|source)\s*[:：]\s*$", re.I)


def _host(url: str) -> str:
    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def safe_url(url: Any) -> Optional[str]:
    """The https URL itself when it is safe to hand to the app's browser launcher, else None."""
    text = str(url or "").strip()
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname or "." not in parsed.hostname or parsed.username or parsed.password or len(text) > 600:
        return None
    if any(ch in text for ch in (" ", "\n", "\r", "\t", "<", ">", '"', "'")):
        return None
    return text


def site_name(url: str, lang: str) -> str:
    host = _host(url)
    for domain, names in _SITE_NAMES.items():
        if host == domain or host.endswith("." + domain):
            return names.get(lang) or names["en"]
    return host


def _lang(language: Optional[str]) -> str:
    raw = (language or "en").lower()[:2]
    return raw if raw in ("fa", "ar", "en") else "en"


def link(label: str, url: str, kind: str) -> Optional[dict]:
    ok = safe_url(url)
    label = " ".join(str(label or "").split())[:LABEL_MAX]
    return {"label": label, "url": ok, "kind": kind, "host": _host(ok)} if ok and label else None


def provider_label(name: str, specialty: Optional[str], site: str) -> str:
    """«دکتر الف — متخصص پوست — پذیرش۲۴»: the doctor's NAME and SPECIALTY are in the link itself (Javad 2026-11-25), the site last."""
    name = " ".join(str(name or "").split())
    spec = " ".join(str(specialty or "").split())
    parts = [name]
    if spec and spec.replace(" ", "") not in name.replace(" ", ""):
        parts.append(spec)
    parts.append(site)
    return " — ".join(p for p in parts if p)


def links_for_identities(identities: Iterable[Any], language: Optional[str], specialty: Optional[str] = None) -> list[dict]:
    """One provider link per verified result that carries its own page («دکتر الف — متخصص پوست — پذیرش۲۴»)."""
    lang = _lang(language)
    out: list[dict] = []
    seen: set = set()
    for ident in identities or ():
        url = getattr(ident, "source_url", None)
        name = getattr(ident, "canonical_name", None)
        spec = getattr(ident, "specialty_or_service", None) or specialty
        item = link(provider_label(name, spec, site_name(url, lang)), url, KIND_PROVIDER) if url and name else None
        if item:
            # R-120 am.2 (Javad 2026-11-26): ONE bubble - each doctor's name + specialty + place, and RIGHT UNDER it the link to his page
            from backend.app import sedi_copy

            spec_text = " ".join(str(spec or "").split())
            item["title"] = " — ".join(x for x in (" ".join(str(name).split()), spec_text) if x)[:LABEL_MAX]
            place = " ".join(str(getattr(ident, "address", None) or getattr(ident, "city", None) or "").split())
            item["location"] = place[:LABEL_MAX] if place else ""
            note = getattr(ident, "note", None)
            if note:
                item["note"] = str(note)[:200]
            item["link_text"] = sedi_copy.t("care_nav.links.open_on", lang, site=site_name(url, lang))
        if item and item["url"] not in seen:
            seen.add(item["url"])
            out.append(item)
        if len(out) >= MAX_LINKS:
            break
    return out


def links_for_search(pairs: Sequence[tuple], language: Optional[str]) -> list[dict]:
    """The directory's own search pages (nothing verified was found): «جست‌وجو در پذیرش۲۴»."""
    lang = _lang(language)
    from backend.app import sedi_copy

    out: list[dict] = []
    for _label, url in pairs or ():
        item = link(sedi_copy.t("care_nav.links.search_on", lang, site=site_name(str(url), lang)), str(url), KIND_SEARCH)
        if item and all(item["url"] != o["url"] for o in out):
            out.append(item)
        if len(out) >= MAX_LINKS:
            break
    return out


def strip_urls(text: str, links: Sequence[dict], language: Optional[str]) -> str:
    """The bubble text WITHOUT the raw URLs of ``links`` (the app shows them below the bubble): «؛ منبع: URL» segments and «• سایت: URL»
    lines disappear, a stray URL is dropped, and ONE catalog line says where the links are. Text without any of those URLs is unchanged."""
    urls = [str(item.get("url") or "") for item in links or () if item.get("url")]
    if not text or not urls or not any(u in text for u in urls):
        return text
    lang = _lang(language)
    from backend.app import sedi_copy

    # the label of a link-only line is a SITE name («• پذیرش۲۴: https://…») or the link's own label - never a doctor's description
    labels = {name for names in _SITE_NAMES.values() for name in names.values()} | {str(item.get("label") or "") for item in links or ()}
    label_rx = "|".join(re.escape(x) for x in sorted((x for x in labels if x), key=len, reverse=True)) or "(?!)"
    lines_out: list[str] = []
    for line in text.split("\n"):
        if not any(u in line for u in urls):
            lines_out.append(line)
            continue
        # a line that is ONLY a link («• پذیرش۲۴: https://…» or the bare URL) moves below the bubble; a doctor's line that merely ends with its
        # source («… ؛ منبع: https://…») keeps everything before it - a sparse entry must not vanish (Codex P2, PR 214)
        if any(re.match(r"^\s*(?:[•\-*]\s*)?(?:(?:" + label_rx + r")\s*[:：]\s*)?" + re.escape(u) + r"\s*$", line) for u in urls):
            continue
        cleaned = line
        for u in urls:
            cleaned = cleaned.replace(u, "")
        cleaned = _SOURCE_LEAD.sub("", cleaned.rstrip()).rstrip(" ؛;،,:")
        if cleaned.strip():
            lines_out.append(cleaned)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines_out)).strip()
    pointer = sedi_copy.t("care_nav.links.below", lang)
    return (body + "\n\n" + pointer) if body else pointer


def reply_with_links(text: str, links: Optional[Sequence[dict]], supports_links: Optional[bool], language: Optional[str]) -> tuple:
    """(reply text, links or None) for the chat API: the links are always returned (an old app ignores the field); only an app that says it
    can show them (``supports_links``) gets the bubble text WITHOUT the raw URLs."""
    items = [dict(item) for item in (links or ()) if item and item.get("url")]
    if not items:
        return text, None
    return (strip_urls(text, items, language) if supports_links else text), items
