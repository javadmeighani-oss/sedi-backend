"""On-demand web lookup that fills the governed I5 directory (D-016).

Used only when the governed directory has too few results for a care-navigation request.
It is not a second store: validated results are written into the same directory tables
(source_system_label=web_lookup) and served by the existing directory service.

Privacy: the outbound query is built ONLY from structured fields (entity, specialty, city,
province, language). The user's message text or any health detail is never sent.
Results are accepted only from trusted domains; nothing is invented. Behind a flag (default OFF).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
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

# Trusted listing / official domains. Exact host or any subdomain matches.
TRUSTED_DOMAINS: dict[str, tuple[str, ...]] = {
    "IR": ("paziresh24.com", "drdr.ir", "doctoreto.com", "nobat.ir", "irimc.org", "behdasht.gov.ir"),
    "*": ("nhs.uk", "who.int"),
}
# Official suffixes (government / academic) are trusted in every country.
TRUSTED_SUFFIXES: tuple[str, ...] = (".gov.ir", ".ac.ir", ".gov", ".edu", ".nhs.uk")

_lock = threading.Lock()
_usage: dict[str, int] = {}


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


def is_trusted_url(url: str, country: str = "IR") -> bool:
    host = (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    if not host:
        return False
    extra = tuple(d.strip().lower() for d in os.getenv(EXTRA_DOMAINS_ENV, "").split(",") if d.strip())
    domains = TRUSTED_DOMAINS.get(country.upper(), ()) + TRUSTED_DOMAINS["*"] + extra
    if any(host == d or host.endswith("." + d) for d in domains):
        return True
    return any(host.endswith(s) for s in TRUSTED_SUFFIXES)


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
    what = f"{specialty} {fa}" if specialty and country.upper() == "IR" else (f"{specialty} {en}" if specialty else en)
    where = ", ".join(x for x in (city, province) if x)
    return f"{what} {where}" if country.upper() == "IR" else f"{what} in {where}"


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
        + ". Never invent providers, phones or addresses. Return at most 8 results."
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
    """Trusted source + matching city + something actionable. Mobile numbers dropped."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items:
        name = " ".join(str(it.get("name") or "").split())
        url = str(it.get("source_url") or "").strip()
        if not name or not is_trusted_url(url, country):
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
                    "city": item_city or city, "address": address, "phone": phone, "source_url": url})
        if len(out) >= MAX_RESULTS:
            break
    return out


def source_domain(canonical_directory_key: str) -> Optional[str]:
    parts = (canonical_directory_key or "").split(":")
    return parts[1] if len(parts) >= 3 and parts[0] == WEB_LOOKUP_SOURCE else None


def to_directory_records(results: Sequence[dict[str, Any]], *, entity: str, province: Optional[str],
                         country: str = "IR") -> list[dict[str, Any]]:
    records = []
    for r in results:
        host = (urlparse(r["source_url"]).hostname or "").lower().removeprefix("www.")
        digest = hashlib.sha256(r["source_url"].encode("utf-8")).hexdigest()[:24]
        base = {
            "city": r["city"], "province": province, "phone": r["phone"], "address": r["address"],
            "source_system_label": WEB_LOOKUP_SOURCE,
            "canonical_directory_key": f"{WEB_LOOKUP_SOURCE}:{host}:{digest}"[:128],
        }
        if entity == "SPECIALIST":
            records.append({**base, "entity_family": "DOCTOR", "full_name": r["name"], "specialty": r["specialty"]})
        elif entity in {"HOSPITAL", "SPECIALTY_CENTER"}:
            records.append({**base, "entity_family": "HOSPITAL", "name": r["name"],
                            "facility_type": "HOSPITAL" if entity == "HOSPITAL" else "MEDICAL_CENTER"})
    return records


def lookup_and_store(db: Any, *, entity: str, specialty: Optional[str], city: Optional[str],
                     province: Optional[str], country: str = "IR", client: Any = None) -> list[str]:
    """Run one guarded lookup, store validated records, return their canonical keys. Never raises."""
    if entity == "LABORATORY" or not web_lookup_enabled():
        return []
    query = build_query(entity, specialty, city, province, country)
    if not query or not _take_quota():
        return []
    try:
        raw = _call_web_search(query, country, client)
        records = to_directory_records(validate_results(raw, city=city, country=country),
                                       entity=entity, province=province, country=country)
        if not records:
            return []
        from backend.app import models
        from backend.app.services.i5.iran_directory_import import apply_plan

        apply_plan(db, records)
        now = datetime.utcnow()
        keys = [r["canonical_directory_key"] for r in records]
        for cls in (models.IranDoctor, models.IranHospital):
            for row in db.query(cls).filter(cls.canonical_directory_key.in_(keys)).all():
                row.last_verified_at = now  # re-confirmed today even if unchanged
        db.flush()
        return keys
    except Exception:  # noqa: BLE001 — lookup is optional; the governed answer path must not break
        return []


def is_stale_web_row(source_system_label: Optional[str], last_verified_at: Any) -> bool:
    if source_system_label != WEB_LOOKUP_SOURCE:
        return False
    if isinstance(last_verified_at, str):
        try:
            last_verified_at = datetime.fromisoformat(last_verified_at)
        except ValueError:
            return True
    return not last_verified_at or last_verified_at < datetime.utcnow() - timedelta(days=FRESH_DAYS)
