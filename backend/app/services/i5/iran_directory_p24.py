"""Public-directory acquisition from Paziresh24 (commercial platform, D-013).

Facts only (name, specialty, city, province, address, landline phone) with attribution through
source_system_label and a key that carries the platform slug (the public page is the reference).
Personal mobile numbers are never stored. Pure parsing + bounded polite crawl; no DB, no scheduling.
"""
from __future__ import annotations

import json
import re
import time
from html import unescape
from typing import Any, Callable, Iterable, Optional
from urllib.parse import unquote, urlparse

P24_SOURCE = "paziresh24_public_directory"
P24_HOST = "www.paziresh24.com"
P24_SITEMAP_INDEX = "https://www.paziresh24.com/sitemap.xml"
P24_DOCTOR_PREFIX = "https://www.paziresh24.com/dr/"
USER_AGENT = "SediKB/1.0 (governed-directory; +https://sedi.health)"
MIN_INTERVAL_SECONDS = 3.0
MAX_KEY_LEN = 128

HttpGet = Callable[..., Any]

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_LOC = re.compile(r"<loc>([^<]+)</loc>")
_DIGITS_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# Order matters: first match wins. Platform "center type" is unreliable (hospitals appear as «مطب»),
# so facility class comes from the name.
_FACILITY_RULES: tuple[tuple[str, str, str], ...] = (
    ("بیمارستان", "HOSPITAL", "HOSPITAL"),
    ("آزمایشگاه", "LABORATORY", "LABORATORY"),
    ("پاتولوژی", "LABORATORY", "LABORATORY"),
    ("رادیولوژی", "LABORATORY", "LABORATORY"),
    ("سونوگرافی", "LABORATORY", "LABORATORY"),
    ("تصویربرداری", "LABORATORY", "LABORATORY"),
    ("کلینیک", "HOSPITAL", "MEDICAL_CENTER"),
    ("درمانگاه", "HOSPITAL", "MEDICAL_CENTER"),
    ("مرکز درمانی", "HOSPITAL", "MEDICAL_CENTER"),
    ("مرکز جامع", "HOSPITAL", "MEDICAL_CENTER"),
)


def classify_facility(name: str) -> Optional[tuple[str, str]]:
    """(entity_family, facility_type) for facility-like names; None for a doctor's private office."""
    for needle, family, ftype in _FACILITY_RULES:
        if needle in (name or ""):
            return family, ftype
    return None


def clean_landline(*values: Any) -> Optional[str]:
    """First landline-looking number; mobile (09…) and unusable numbers are dropped."""
    for value in values:
        for part in re.split(r"[,،/\n]|(?<=\d)\s+(?=0)", str(value or "")):
            digits = re.sub(r"\D", "", part.translate(_DIGITS_FA))
            if len(digits) < 8 or digits.startswith(("09", "989", "00989")) or "0000000" in digits:
                continue  # too short, mobile, or a placeholder such as 05100000000
            if len(digits) > 11:
                if digits.startswith("0") and len(digits) % 11 == 0:
                    digits = digits[:11]  # two numbers concatenated by the source
                else:
                    continue
            return digits if digits.startswith("0") else "0" + digits if len(digits) == 10 else digits
    return None


def parse_sitemap(xml: bytes | str) -> list[str]:
    text = xml.decode("utf-8", "replace") if isinstance(xml, bytes) else xml
    return [unescape(u).strip() for u in _LOC.findall(text)]


def _page_props(html: bytes | str) -> dict[str, Any]:
    text = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    m = _NEXT_DATA.search(text)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))["props"]["pageProps"]
    except (KeyError, ValueError, TypeError):
        return {}


def _is_number(v: Any) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def _center_record(center: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Facility record from a center object; None for private offices and online services."""
    if int(center.get("type_id") or 0) == 3:  # online-visit pseudo center
        return None
    name = " ".join(str(center.get("name") or "").split())
    cls = classify_facility(name)
    if not cls or not center.get("id"):
        return None
    family, ftype = cls
    rec: dict[str, Any] = {
        "entity_family": family,
        "name": name,
        "city": center.get("city"),
        "province": center.get("province"),
        "phone": clean_landline(*(center.get("tell") or []), center.get("display_number")),
        "address": " ".join(str(center.get("address") or "").split())[:512] or None,
        "source_system_label": P24_SOURCE,
        "canonical_directory_key": f"{P24_SOURCE}:center:{center['id']}",
    }
    if family == "HOSPITAL":
        rec["facility_type"] = ftype
    return rec


def parse_doctor_page(html: bytes | str) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """(doctor record or None, facility records found in the doctor's centers)."""
    pp = _page_props(html)
    info = pp.get("information") or {}
    slug = pp.get("slug") or ""
    name = " ".join(str(info.get("display_name") or "").split())
    centers = [c for c in (pp.get("centers") or []) if isinstance(c, dict)]
    facilities = [r for r in (_center_record(c) for c in centers) if r]
    if not name or not slug:
        return None, facilities
    key = f"{P24_SOURCE}:dr:{slug}"
    if len(key) > MAX_KEY_LEN:
        return None, facilities
    physical = [c for c in centers if int(c.get("type_id") or 0) != 3]
    # Bulk-imported listings are inactive for booking but still carry the listed address/phone.
    office = next((c for c in physical if c.get("is_active")), physical[0] if physical else None)
    exps = (pp.get("expertises") or {}).get("expertises") or []
    specialty = " ".join(str(exps[0].get("alias_title") or "").split()) if exps else None
    fb = (pp.get("feedbacks") or {}).get("details") or {}
    rates = [float(v) for v in (fb.get("average_rates") or {}).values() if _is_number(v)]
    doctor = {
        "entity_family": "DOCTOR",
        "full_name": name,
        "specialty": specialty or None,
        "city": (office or {}).get("city"),
        "province": (office or {}).get("province"),
        "phone": clean_landline(*((office or {}).get("tell") or [])),
        "address": " ".join(str((office or {}).get("address") or "").split())[:512] or None,
        "source_system_label": P24_SOURCE,
        "canonical_directory_key": key,
        "rating_avg": round(sum(rates) / len(rates), 2) if rates else None,
        "rating_count": fb.get("count_of_feedbacks"),
        "satisfaction_percent": fb.get("satisfaction_percent"),
    }
    if not (doctor["address"] or doctor["phone"]):
        return None, facilities  # nothing a patient can act on
    return doctor, facilities


def parse_center_page(html: bytes | str) -> Optional[dict[str, Any]]:
    """Facility record from a /center/ page; None for offices or unusable pages."""
    pp = _page_props(html)
    for q in (pp.get("dehydratedState") or {}).get("queries") or []:
        if (q.get("queryKey") or [""])[0] != "slugProfile":
            continue
        data = (((q.get("state") or {}).get("data") or {}).get("result") or {}).get("data") or {}
        if not data.get("id"):
            return None
        return _center_record({
            "id": data["id"], "name": data.get("name"), "city": data.get("city"), "province": data.get("province"),
            "address": data.get("address"), "tell": [data.get("tell")] if data.get("tell") else [],
            "display_number": data.get("display_number"), "type_id": 0,
        })
    return None


def _default_get(url: str, *, timeout: int = 60, attempts: int = 4):
    """urllib GET with retries: the platform sometimes truncates large bodies (IncompleteRead)."""
    import urllib.request
    from types import SimpleNamespace

    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return SimpleNamespace(status_code=int(resp.status), content=resp.read(), url=resp.geturl())
        except Exception as exc:  # noqa: BLE001 — includes http.client.IncompleteRead
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise OSError(f"P24_FETCH_FAILED:{last}")


def list_doctor_urls(http_get: HttpGet = _default_get) -> list[str]:
    """All doctor page URLs from the public sitemap index (robots allows)."""
    out: list[str] = []
    for sm in parse_sitemap(http_get(P24_SITEMAP_INDEX).content):
        if "doctors-url" in sm:
            out.extend(parse_sitemap(http_get(sm).content))
    return out


def crawl_doctors(
    urls: Iterable[str],
    *,
    http_get: HttpGet = _default_get,
    budget: int = 100,
    interval: float = MIN_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Fetch at most `budget` doctor pages; failures are counted, never guessed."""
    doctors: dict[str, dict[str, Any]] = {}
    facilities: dict[str, dict[str, Any]] = {}
    stats = {"fetched": 0, "failed": 0, "no_record": 0}
    for url in urls:
        if stats["fetched"] + stats["failed"] >= budget:
            break
        if (urlparse(url).hostname or "") != P24_HOST or not unquote(url).startswith(unquote(P24_DOCTOR_PREFIX)):
            stats["failed"] += 1
            continue
        try:
            resp = http_get(url)
            if int(getattr(resp, "status_code", 0) or 0) != 200:
                raise OSError("status")
            doctor, facs = parse_doctor_page(resp.content)
            stats["fetched"] += 1
        except Exception:  # noqa: BLE001 — one bad page must not stop the run
            stats["failed"] += 1
            sleep(interval)
            continue
        if doctor:
            doctors[doctor["canonical_directory_key"]] = doctor
        else:
            stats["no_record"] += 1
        for fac in facs:
            facilities[fac["canonical_directory_key"]] = fac
        sleep(interval)
    return {"records": list(doctors.values()) + list(facilities.values()), "stats": stats}
