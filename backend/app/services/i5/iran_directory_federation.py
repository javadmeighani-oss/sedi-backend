"""Federated official provider-web acquisition for Iran facility directories.

CAP25 seed member: Shahid Beheshti University of Medical Sciences (SBMU)
official Virtual Tour page listing affiliated hospitals / medical centers.

Coverage class: OFFICIAL_FEDERATED_SEED / PARTIAL_GOVERNED_COVERAGE (not nationwide).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from backend.app.services.i5.iran_directory_source_manifest import SBMU_FED_HOSPITAL_SOURCE

HttpGet = Callable[..., Any]

SBMU_VIRTUAL_TOUR_HOSPITALS_URL = (
    "https://sbmu.ac.ir/Virtual_Tour/%D8%A8%DB%8C%D9%85%D8%A7%D8%B1%D8%B3%D8%AA%D8%A7%D9%86"
)

# Verified against official SBMU Virtual Tour page (Gate-02 probe). Each name
# must appear in the live page body before the record is emitted.
SBMU_HOSPITAL_SEED: tuple[dict[str, str], ...] = (
    {"name": "اختر", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "امام حسین", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "آیت الله طالقانی", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "دکتر مسیح دانشوری", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "شهدای تجریش", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "شهید لبافی نژاد", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "شهید مدرس", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "طرفه", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "لقمان حکیم", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "مفید", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "مهدیه", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "پانزده خرداد", "facility_type": "HOSPITAL", "city": "تهران"},
    {"name": "امام خمینی فیروزکوه", "facility_type": "MEDICAL_CENTER", "city": "فیروزکوه"},
    {"name": "انصار الغدیر", "facility_type": "MEDICAL_CENTER", "city": "تهران"},
    {"name": "حضرت فاطمه دماوند", "facility_type": "MEDICAL_CENTER", "city": "دماوند"},
    {"name": "سوم شعبان دماوند", "facility_type": "MEDICAL_CENTER", "city": "دماوند"},
    {"name": "شهدای پاکدشت", "facility_type": "MEDICAL_CENTER", "city": "پاکدشت"},
    {"name": "شهدای گمنام", "facility_type": "MEDICAL_CENTER", "city": "تهران"},
    {"name": "شهید ستاری قرچک", "facility_type": "MEDICAL_CENTER", "city": "قرچک"},
    {"name": "زعیم پاکدشت", "facility_type": "MEDICAL_CENTER", "city": "پاکدشت"},
    {"name": "مفتح ورامین", "facility_type": "MEDICAL_CENTER", "city": "ورامین"},
)


@dataclass(frozen=True)
class FederationFetchResult:
    source_url: str
    final_url: str
    status_code: int
    body: bytes
    records: list[dict[str, Any]]
    rejected: list[dict[str, Any]]
    coverage_class: str = "OFFICIAL_FEDERATED_SEED"


def _slug(name: str) -> str:
    cleaned = re.sub(r"\s+", "_", name.strip())
    return cleaned[:80]


def _name_present(page_text: str, name: str) -> bool:
    # Official page may omit some diacritic/parenthetical variants; require core tokens.
    tokens = [t for t in re.split(r"\s+", name) if t and t not in {"(ع)", "(ره)", "(س)"}]
    return all(token in page_text for token in tokens)


def parse_sbmu_affiliated_facilities(html: bytes | str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = html.decode("utf-8", "replace") if isinstance(html, bytes) else html
    plain = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    plain = re.sub(r"<style[\s\S]*?</style>", " ", plain, flags=re.I)
    plain = re.sub(r"<[^>]+>", " ", plain)
    plain = " ".join(plain.split())
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for seed in SBMU_HOSPITAL_SEED:
        name = seed["name"]
        if not _name_present(plain, name):
            rejected.append({"name": name, "reason": "NAME_NOT_OBSERVED_ON_OFFICIAL_PAGE"})
            continue
        display = f"بیمارستان {name}" if seed["facility_type"] == "HOSPITAL" else f"مرکز درمانی {name}"
        records.append(
            {
                "entity_family": "HOSPITAL",
                "name": display,
                "facility_type": seed["facility_type"],
                "city": seed["city"],
                "province": "تهران",
                "source_system_label": SBMU_FED_HOSPITAL_SOURCE,
                "canonical_directory_key": f"{SBMU_FED_HOSPITAL_SOURCE}:{_slug(name)}",
                "record_state": "ACTIVE",
                "source_page_url": SBMU_VIRTUAL_TOUR_HOSPITALS_URL,
            }
        )
    return records, rejected


def _default_http_get(url: str, *, timeout: int = 30, headers: Optional[dict[str, str]] = None, allow_redirects: bool = True):
    """Prefer urllib for SBMU TLS quirks; fall back to requests only if needed."""
    import urllib.error
    import urllib.request
    from types import SimpleNamespace

    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return SimpleNamespace(status_code=int(resp.status), content=body, url=resp.geturl())
    except urllib.error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        return SimpleNamespace(status_code=int(exc.code), content=body or b"", url=url)
    except Exception:
        import requests

        return requests.get(url, timeout=timeout, headers=headers or {}, allow_redirects=allow_redirects)


def acquire_sbmu_affiliated_hospitals(
    *,
    http_get: Optional[HttpGet] = None,
    timeout: int = 30,
) -> FederationFetchResult:
    """Fetch official SBMU page and emit verified facility facts only."""
    getter = http_get or _default_http_get
    candidates = (
        SBMU_VIRTUAL_TOUR_HOSPITALS_URL,
        "https://www.sbmu.ac.ir/Virtual_Tour/%D8%A8%DB%8C%D9%85%D8%A7%D8%B1%D8%B3%D8%AA%D8%A7%D9%86",
    )
    last_error: Exception | None = None
    resp = None
    used_url = candidates[0]
    for url in candidates:
        try:
            used_url = url
            resp = getter(
                url,
                timeout=timeout,
                headers={"User-Agent": "SediKB/1.0 (governed-directory-federation)"},
                allow_redirects=True,
            )
            if int(getattr(resp, "status_code", 0) or 0) == 200:
                break
        except Exception as exc:  # noqa: BLE001 — try next candidate
            last_error = exc
            resp = None
    if resp is None:
        raise ValueError(f"FEDERATION_FETCH_FAILED:{last_error}")
    status = int(getattr(resp, "status_code", 0) or 0)
    body = getattr(resp, "content", b"") or b""
    if isinstance(body, str):
        body = body.encode("utf-8", errors="replace")
    final_url = str(getattr(resp, "url", used_url) or used_url)
    host = (urlparse(final_url).hostname or "").lower()
    if not host.endswith("sbmu.ac.ir"):
        raise ValueError(f"FEDERATION_HOST_MISMATCH:{host}")
    if status != 200:
        raise ValueError(f"FEDERATION_HTTP_{status}")
    records, rejected = parse_sbmu_affiliated_facilities(body)
    if not records:
        raise ValueError("FEDERATION_ZERO_VERIFIED_RECORDS")
    return FederationFetchResult(
        source_url=used_url,
        final_url=final_url,
        status_code=status,
        body=body,
        records=records,
        rejected=rejected,
    )
