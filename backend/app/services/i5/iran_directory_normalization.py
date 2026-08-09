"""Parse and normalize non-clinical Iran directory listings."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlparse

from .iran_directory_source_manifest import IRIMC_SOURCE

FIELD_LIMITS = {
    "canonical_directory_key": 128, "full_name": 256, "name": 256, "specialty": 128,
    "city": 128, "province": 128, "phone": 64, "address": 512, "services_text": 512,
    "source_system_label": 128,
}
_PROFILE_ID = re.compile(r"^[0-9a-fA-F-]{16,64}$")


class _ResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._profile_id: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "tr" and "rowclass" in (values.get("class") or "").split():
            self._row, self._profile_id = [], None
        elif tag == "td" and self._row is not None:
            self._cell = []
        elif tag == "a" and self._row is not None:
            profile_id = parse_qs(urlparse(values.get("href") or "").query).get("id", [None])[0]
            if profile_id:
                self._profile_id = profile_id

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._profile_id:
                self.rows.append(self._row + [self._profile_id])
            self._row = None


def parse_irimc_search_html(html: bytes | str) -> list[dict[str, str | None]]:
    """Parse the IRIMC seven-cell layout without fetching profile pages."""
    parser = _ResultsParser()
    parser.feed(html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html)
    records: list[dict[str, str | None]] = []
    for row in parser.rows:
        if len(row) < 8:
            continue
        first_name, last_name, _mc_code, degree_field, city, _membership, _profile_link = row[:7]
        profile_id = row[-1]
        address = " ".join(cell for cell in row[7:-1] if cell) or None
        records.append({
            "profile_id": profile_id, "full_name": " ".join(part for part in (first_name, last_name) if part),
            "specialty": degree_field or None, "city": city or None, "address": address or None,
        })
    return records


def _clean(value: Any, field: str) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text[: FIELD_LIMITS[field]]


def _normalize_one(raw: dict[str, Any]) -> dict[str, Any]:
    family = str(raw.get("entity_family", "DOCTOR")).strip().upper()
    if family not in {"DOCTOR", "LABORATORY", "HOSPITAL"}:
        raise ValueError("ENTITY_FAMILY_INVALID")
    source = _clean(raw.get("source_system_label") or (IRIMC_SOURCE if family == "DOCTOR" else None), "source_system_label")
    if not source:
        raise ValueError("SOURCE_REQUIRED")
    key = _clean(raw.get("canonical_directory_key"), "canonical_directory_key")
    if family == "DOCTOR" and not key:
        profile_id = _clean(raw.get("profile_id"), "canonical_directory_key")
        if not profile_id or not _PROFILE_ID.fullmatch(profile_id):
            raise ValueError("PROFILE_ID_INVALID")
        key = f"{IRIMC_SOURCE}:{profile_id}"
    if not key:
        raise ValueError("CANONICAL_KEY_REQUIRED")
    name_field = "full_name" if family == "DOCTOR" else "name"
    name = _clean(raw.get(name_field), name_field)
    if not name:
        raise ValueError(f"{name_field.upper()}_REQUIRED")
    normalized = {
        "entity_family": family, "canonical_directory_key": key, name_field: name,
        "city": _clean(raw.get("city"), "city"), "province": _clean(raw.get("province"), "province"),
        "phone": _clean(raw.get("phone"), "phone"), "address": _clean(raw.get("address"), "address"),
        "record_state": "ACTIVE", "source_system_label": source,
    }
    if family == "DOCTOR":
        normalized["specialty"] = _clean(raw.get("specialty"), "specialty")
    elif family == "LABORATORY":
        normalized["services_text"] = _clean(raw.get("services_text"), "services_text")
    else:
        facility_type = str(raw.get("facility_type", "HOSPITAL")).strip().upper()
        if facility_type not in {"HOSPITAL", "MEDICAL_CENTER"}:
            raise ValueError("FACILITY_TYPE_INVALID")
        normalized["facility_type"] = facility_type
    return normalized


def normalize_records(raw_records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid, rejected, seen = [], [], set()
    for raw in raw_records:
        try:
            record = _normalize_one(raw)
            key = (record["entity_family"], record["canonical_directory_key"])
            if key in seen:
                raise ValueError("DUPLICATE_CANONICAL_KEY")
            seen.add(key)
            valid.append(record)
        except (TypeError, ValueError) as exc:
            rejected.append({"record": raw, "reason": str(exc)})
    return valid, rejected
