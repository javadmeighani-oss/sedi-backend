"""Format capability matrix + adaptive adapter-mode routing (no schema change)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from backend.app.services.i5.adapters.base import (
    ADAPTER_MODES,
    AdapterFrameworkError,
    AdapterRegistry,
    default_registry,
)
from backend.app.services.i5.know01.format_contracts import FUTURE_ADAPTER_CONTRACTS, FUTURE_FORMATS


@dataclass(frozen=True)
class FormatCapabilityRow:
    format_id: str
    status: str  # IMPLEMENTED | CONTRACT_ONLY | UNSUPPORTED | NOT_CURRENTLY_REQUIRED
    implementation_path: str
    test_coverage: str
    current_trusted_source_need: str
    fail_closed_behavior: str
    production_required_for_v1: str  # YES|NO


def build_format_capability_matrix(
    *,
    registry: Optional[AdapterRegistry] = None,
) -> List[FormatCapabilityRow]:
    reg = registry or default_registry()
    implemented_modes = {a.metadata().mode for a in (reg.get(i) for i in reg.list_ids())}

    rows: List[FormatCapabilityRow] = []

    def add(
        fmt: str,
        status: str,
        path: str,
        tests: str,
        need: str,
        fail: str,
        prod: str,
    ) -> None:
        rows.append(
            FormatCapabilityRow(
                format_id=fmt,
                status=status,
                implementation_path=path,
                test_coverage=tests,
                current_trusted_source_need=need,
                fail_closed_behavior=fail,
                production_required_for_v1=prod,
            )
        )

    # Runtime adapter modes
    mode_meta = {
        "OFFICIAL_API": (
            "IMPLEMENTED" if "OFFICIAL_API" in implemented_modes else "UNSUPPORTED",
            "adapters/official_api.py",
            "test_i5_know01_*; test_section30_i5_w3_p01*",
            "PubMed E-utilities / openFDA / CT.gov JSON APIs",
            "INVALID_CONTENT_TYPE / GOVERNANCE_BLOCKED / ADAPTER_UNKNOWN",
            "YES",
        ),
        "OFFICIAL_XML": (
            "IMPLEMENTED" if "OFFICIAL_XML" in implemented_modes else "UNSUPPORTED",
            "adapters/pdf_jats.py::JatsXmlAdapter",
            "test_i5_know01_*; know04 PMC/JATS",
            "PMC JATS XML",
            "UNSUPPORTED_FORMAT / PARSING_FAILED",
            "YES",
        ),
        "OFFICIAL_JSON": (
            "CONTRACT_ONLY",
            "ADAPTER_MODES contains OFFICIAL_JSON; OfficialApiAdapter covers JSON APIs under OFFICIAL_API",
            "mode listed; no dedicated OFFICIAL_JSON adapter id",
            "Covered via OFFICIAL_API for approved JSON APIs",
            "ADAPTER_UNKNOWN if resolved by mode alone",
            "NO",
        ),
        "RSS_OR_FEED": (
            "IMPLEMENTED" if "RSS_OR_FEED" in implemented_modes else "UNSUPPORTED",
            "adapters/rss_feed.py",
            "test_i5_know01_*; w3_p01",
            "WHO news / guideline feeds",
            "UNSUPPORTED_FORMAT / PARSING_FAILED",
            "YES",
        ),
        "PUBLIC_WEB_FETCH": (
            "IMPLEMENTED" if "PUBLIC_WEB_FETCH" in implemented_modes else "UNSUPPORTED",
            "adapters/public_web_fetch.py",
            "w3_p01 + know01",
            "Official HTML discovery pages",
            "GOVERNANCE_BLOCKED / UNSAFE_URL",
            "YES",
        ),
        "PDF_TEXT": (
            "IMPLEMENTED" if "PDF_TEXT" in implemented_modes else "UNSUPPORTED",
            "adapters/pdf_jats.py::PdfTextAdapter",
            "know01 pdf oversized + extract tests",
            "PMC/open PDFs with extractable text when rights allow",
            "CONTENT_TOO_LARGE / EXTRACTION_FAILED",
            "YES",
        ),
        "MANUAL_OR_LINK_ONLY": (
            "UNSUPPORTED",
            "adapters/base.py::resolve_by_mode",
            "explicit ADAPTER_DISABLED",
            "Not auto-ingested",
            "ADAPTER_DISABLED",
            "NO",
        ),
        "BLOCKED_OR_EXCLUDED": (
            "UNSUPPORTED",
            "adapters/base.py::resolve_by_mode",
            "explicit ADAPTER_DISABLED",
            "Blocked sources",
            "ADAPTER_DISABLED",
            "NO",
        ),
    }
    for mode in sorted(ADAPTER_MODES):
        status, path, tests, need, fail, prod = mode_meta[mode]
        add(mode, status, path, tests, need, fail, prod)

    # Practical aliases required by Gate evaluation
    add(
        "HTML",
        "IMPLEMENTED",
        "adapters/public_web_fetch.py",
        "w3_p01",
        "Official HTML pages",
        "GOVERNANCE_BLOCKED",
        "YES",
    )
    add(
        "JSON",
        "IMPLEMENTED",
        "adapters/official_api.py (OFFICIAL_API)",
        "know04 connectors",
        "Official JSON APIs",
        "INVALID_CONTENT_TYPE",
        "YES",
    )
    add(
        "JATS_XML",
        "IMPLEMENTED",
        "adapters/pdf_jats.py::JatsXmlAdapter",
        "know04 PMC",
        "PMC JATS",
        "PARSING_FAILED",
        "YES",
    )
    add(
        "ATOM",
        "IMPLEMENTED",
        "adapters/rss_feed.py (RSS_OR_FEED handles Atom fixtures)",
        "rss_feed adapter",
        "Guideline/news Atom where present",
        "PARSING_FAILED",
        "YES",
    )

    for fmt in FUTURE_FORMATS:
        # Runtime RSS/ATOM exist under RSS_OR_FEED; KNOW-01 FUTURE contracts remain fail-closed stubs.
        if fmt in {"RSS", "ATOM"}:
            add(
                f"FUTURE_CONTRACT:{fmt}",
                "CONTRACT_ONLY",
                "know01/format_contracts.py (stub) — runtime via RSS_OR_FEED",
                "test_know01_future_format_contracts",
                "Runtime covered by RSS_OR_FEED; stub proves insertion point",
                "UNSUPPORTED_FORMAT from FUTURE contract",
                "NO",
            )
            continue
        if fmt == "OAI_PMH":
            need = "PMC OAI connector exists in KNOW-04; FUTURE contract remains fail-closed stub"
            prod = "YES"
            status = "CONTRACT_ONLY"
        elif fmt == "BITS_XML":
            need = "NCBI Bookshelf BITS when rights allow; not required until approved book fulltext path"
            prod = "NO"
            status = "NOT_CURRENTLY_REQUIRED"
        elif fmt in {"PDF_SCANNED", "OCR", "IMAGE"}:
            need = "Conservative — no unsafe OCR for V1 completeness claims"
            prod = "NO"
            status = "NOT_CURRENTLY_REQUIRED"
        elif fmt in {"CSV", "TSV"}:
            need = "Not required by current approved connector universe"
            prod = "NO"
            status = "NOT_CURRENTLY_REQUIRED"
        elif fmt == "EPUB":
            need = "Not required by current approved V1 sources"
            prod = "NO"
            status = "NOT_CURRENTLY_REQUIRED"
        else:
            need = "Not required by current approved V1 source universe"
            prod = "NO"
            status = "NOT_CURRENTLY_REQUIRED"
        add(
            fmt,
            status if status != "CONTRACT_ONLY" else "CONTRACT_ONLY",
            f"know01/format_contracts.py::{FUTURE_ADAPTER_CONTRACTS[fmt].__class__.__name__}",
            "test_know01_future_format_contracts + foundation gate",
            need,
            "UNSUPPORTED_FORMAT (durable via AdapterFrameworkError; no silent discard)",
            prod,
        )

    return rows


def matrix_as_dicts() -> List[Dict[str, Any]]:
    return [asdict(r) for r in build_format_capability_matrix()]


def assert_v1_required_formats_covered(rows: Optional[Sequence[FormatCapabilityRow]] = None) -> None:
    rows = list(rows or build_format_capability_matrix())
    by_id = {r.format_id: r for r in rows}
    required = ("OFFICIAL_API", "OFFICIAL_XML", "RSS_OR_FEED", "PUBLIC_WEB_FETCH", "PDF_TEXT", "HTML", "JSON", "JATS_XML")
    for fmt in required:
        row = by_id[fmt]
        if row.status != "IMPLEMENTED":
            raise AssertionError(f"V1_REQUIRED_FORMAT_NOT_IMPLEMENTED:{fmt}:{row.status}")


def select_adapter_mode(
    *,
    content_type: Optional[str] = None,
    filename_hint: Optional[str] = None,
    declared_format: Optional[str] = None,
    payload_prefix: Optional[bytes] = None,
) -> str:
    """Adaptive mode selection — Content-Type / payload / declared format over extension alone."""
    ctype = (content_type or "").split(";", 1)[0].strip().lower()
    declared = (declared_format or "").strip().upper()
    name = (filename_hint or "").lower()
    prefix = payload_prefix or b""

    # Declared registry/source format wins when explicit and known
    declared_map = {
        "JSON": "OFFICIAL_API",
        "OFFICIAL_JSON": "OFFICIAL_API",
        "OFFICIAL_API": "OFFICIAL_API",
        "XML": "OFFICIAL_XML",
        "JATS": "OFFICIAL_XML",
        "JATS_XML": "OFFICIAL_XML",
        "OFFICIAL_XML": "OFFICIAL_XML",
        "RSS": "RSS_OR_FEED",
        "ATOM": "RSS_OR_FEED",
        "RSS_OR_FEED": "RSS_OR_FEED",
        "HTML": "PUBLIC_WEB_FETCH",
        "PUBLIC_WEB_FETCH": "PUBLIC_WEB_FETCH",
        "PDF": "PDF_TEXT",
        "PDF_TEXT": "PDF_TEXT",
        "BITS_XML": "UNSUPPORTED",
        "EPUB": "UNSUPPORTED",
        "OCR": "UNSUPPORTED",
        "PDF_SCANNED": "UNSUPPORTED",
    }
    if declared in declared_map:
        mode = declared_map[declared]
        if mode == "UNSUPPORTED":
            raise AdapterFrameworkError("UNSUPPORTED_FORMAT", declared)
        return mode

    if ctype in {"application/json", "text/json"}:
        return "OFFICIAL_API"
    if ctype in {"application/xml", "text/xml", "application/jats+xml"}:
        return "OFFICIAL_XML"
    if ctype in {"application/rss+xml", "application/atom+xml", "application/feed+json"}:
        return "RSS_OR_FEED"
    if ctype in {"text/html", "application/xhtml+xml"}:
        return "PUBLIC_WEB_FETCH"
    if ctype == "application/pdf":
        return "PDF_TEXT"

    # Payload sniff (safe, bounded)
    head = prefix[:256].lstrip()
    if head.startswith(b"{") or head.startswith(b"["):
        return "OFFICIAL_API"
    if head.startswith(b"%PDF"):
        return "PDF_TEXT"
    if head.startswith(b"<?xml") or head.startswith(b"<"):
        low = head[:200].lower()
        if b"<rss" in low or b"<feed" in low or b"atom" in low:
            return "RSS_OR_FEED"
        if b"<article" in low or b"jats" in low:
            return "OFFICIAL_XML"
        if b"<html" in low:
            return "PUBLIC_WEB_FETCH"
        return "OFFICIAL_XML"

    # Filename is last resort — must not override contradictory content-type already handled
    if name.endswith(".json"):
        return "OFFICIAL_API"
    if name.endswith(".pdf"):
        return "PDF_TEXT"
    if name.endswith((".rss", ".atom", ".xml")) and "sitemap" not in name:
        if name.endswith((".rss", ".atom")):
            return "RSS_OR_FEED"
        return "OFFICIAL_XML"
    if name.endswith((".html", ".htm")):
        return "PUBLIC_WEB_FETCH"
    if name.endswith((".epub", ".docx", ".zip")):
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", name.rsplit(".", 1)[-1].upper())

    raise AdapterFrameworkError("UNSUPPORTED_FORMAT", "undetermined")


def resolve_adapter_for_resource(
    registry: AdapterRegistry,
    *,
    content_type: Optional[str] = None,
    filename_hint: Optional[str] = None,
    declared_format: Optional[str] = None,
    payload_prefix: Optional[bytes] = None,
):
    mode = select_adapter_mode(
        content_type=content_type,
        filename_hint=filename_hint,
        declared_format=declared_format,
        payload_prefix=payload_prefix,
    )
    return mode, registry.resolve_by_mode(mode)
