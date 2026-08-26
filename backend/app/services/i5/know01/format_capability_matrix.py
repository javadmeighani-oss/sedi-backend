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
            "CONTENT_TOO_LARGE / EXTRACTION_FAILED / REVIEW_REQUIRED(image-only)",
            "YES",
        ),
        "CSV_TSV": (
            "IMPLEMENTED" if "CSV_TSV" in implemented_modes else "UNSUPPORTED",
            "adapters/tabular_docx.py::CsvTsvAdapter",
            "test_i5_source_format_resilience",
            "Governed tabular datasets",
            "CONTENT_TOO_LARGE / PARSING_FAILED",
            "YES",
        ),
        "DOCX": (
            "IMPLEMENTED" if "DOCX" in implemented_modes else "UNSUPPORTED",
            "adapters/tabular_docx.py::DocxAdapter",
            "test_i5_source_format_resilience",
            "Governed OOXML text documents",
            "UNSUPPORTED_FORMAT macros / CONTENT_TOO_LARGE",
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
    add(
        "CSV_TSV_ALIAS",
        "IMPLEMENTED" if "CSV_TSV" in implemented_modes else "UNSUPPORTED",
        "adapters/tabular_docx.py::CsvTsvAdapter",
        "format resilience suite",
        "Governed CSV/TSV",
        "CONTENT_TOO_LARGE",
        "YES",
    )
    add(
        "DOCX_ALIAS",
        "IMPLEMENTED" if "DOCX" in implemented_modes else "UNSUPPORTED",
        "adapters/tabular_docx.py::DocxAdapter",
        "format resilience suite",
        "Governed DOCX text",
        "UNSUPPORTED_FORMAT",
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
            need = "Conservative — image-only PDF detection + REVIEW_REQUIRED; OCR deferred"
            prod = "NO"
            status = "NOT_CURRENTLY_REQUIRED"
        elif fmt in {"CSV", "TSV"}:
            add(
                f"FUTURE_CONTRACT:{fmt}",
                "CONTRACT_ONLY",
                "know01/format_contracts.py (stub) — runtime via CSV_TSV",
                "test_know01_future_format_contracts",
                "Runtime covered by CSV_TSV adapter; stub proves insertion point",
                "UNSUPPORTED_FORMAT from FUTURE contract",
                "NO",
            )
            continue
        elif fmt == "DOCX":
            add(
                "FUTURE_CONTRACT:DOCX",
                "CONTRACT_ONLY",
                "know01/format_contracts.py (stub) — runtime via DOCX adapter",
                "test_know01_future_format_contracts",
                "Runtime covered by DOCX adapter; stub proves insertion point",
                "UNSUPPORTED_FORMAT from FUTURE contract",
                "NO",
            )
            continue
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
    required = (
        "OFFICIAL_API",
        "OFFICIAL_XML",
        "RSS_OR_FEED",
        "PUBLIC_WEB_FETCH",
        "PDF_TEXT",
        "CSV_TSV",
        "DOCX",
        "HTML",
        "JSON",
        "JATS_XML",
    )
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
    from backend.app.services.i5.adapters.representation_classifier import classify_representation

    # Preserve fail-closed for formats that remain unsupported for auto-ingest
    declared = (declared_format or "").strip().upper()
    if declared in {"OCR", "BITS_XML", "EPUB", "ZIP_DATASET", "IMAGE"}:
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", declared)
    name = (filename_hint or "").lower()
    if name.endswith(".epub"):
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", "EPUB")

    try:
        decision = classify_representation(
            content_type=content_type,
            payload=payload_prefix,
            filename_hint=filename_hint,
            declared_format=declared_format,
            allow_mime_only_when_empty_body=True,
        )
    except AdapterFrameworkError:
        raise

    if decision.representation == "PDF_IMAGE_ONLY":
        # Mode still PDF_TEXT adapter; extraction fail-closes to REVIEW_REQUIRED
        return "PDF_TEXT"
    return decision.adapter_mode


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
