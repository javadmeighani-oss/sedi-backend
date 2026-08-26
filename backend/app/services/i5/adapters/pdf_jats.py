"""PDF text + JATS XML adapters (fixture + controlled live HTTPS).

Scanned/image-only PDF → REVIEW_REQUIRED / fail-closed (no automatic OCR).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional, Sequence
from xml.etree.ElementTree import ParseError

from backend.app.schemas.i5_adapters import AdapterMetadata, FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_CONTENT_BYTES,
    AdapterFrameworkError,
    FixtureTransport,
    SourceAdapter,
    assert_source_governance_allows_controlled_use,
    build_fetch_envelope,
)
from backend.app.services.i5.adapters.live_fetch import fetch_live_envelope
from backend.app.services.i5.adapters.live_transport import HttpGet

PDF_ADAPTER_ID = "i5.pdf_text"
PDF_ADAPTER_VERSION = "fmt-resilience-v1"
JATS_ADAPTER_ID = "i5.jats_xml"
JATS_ADAPTER_VERSION = "fmt-resilience-v1"

MAX_PDF_PAGES = 50


def detect_pdf_image_only(body: bytes) -> bool:
    """True when PDF appears scanned/image-only (no extractable text). No OCR."""
    if b"%SEDI_PDF_TEXT_FIXTURE%" in body:
        return False
    if b"%SEDI_PDF_IMAGE_ONLY_FIXTURE%" in body:
        return True
    if not body.lstrip().startswith(b"%PDF"):
        return False
    try:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(body))
        if len(reader.pages) == 0:
            return False
        if len(reader.pages) > MAX_PDF_PAGES:
            raise AdapterFrameworkError("CONTENT_TOO_LARGE", "PDF_PAGES")
        texts = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            texts.append((page.extract_text() or "").strip())
        joined = "\n".join(t for t in texts if t).strip()
        return len(joined) < 20
    except ImportError:
        # Without pypdf, only explicit fixture marker proves image-only
        return False
    except AdapterFrameworkError:
        raise
    except Exception:
        return False


def extract_pdf_text(body: bytes) -> str:
    """Best-effort PDF text extraction.

    Prefer pypdf when installed; otherwise accept controlled fixtures that embed
    plain text after a %SEDI_PDF_TEXT_FIXTURE% marker (CI-safe).
    Image-only/scanned PDFs fail closed with REVIEW_REQUIRED (no OCR).
    """
    if b"%SEDI_PDF_IMAGE_ONLY_FIXTURE%" in body:
        raise AdapterFrameworkError("REVIEW_REQUIRED", "PDF_IMAGE_ONLY")
    if detect_pdf_image_only(body):
        raise AdapterFrameworkError("REVIEW_REQUIRED", "PDF_IMAGE_ONLY")
    if b"%SEDI_PDF_TEXT_FIXTURE%" in body:
        return body.split(b"%SEDI_PDF_TEXT_FIXTURE%", 1)[1].decode("utf-8", errors="replace").strip()
    if not body.lstrip().startswith(b"%PDF") and b"%SEDI_PDF_TEXT_FIXTURE%" not in body:
        raise AdapterFrameworkError("INVALID_CONTENT_TYPE", "NOT_PDF")
    try:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(body))
        if len(reader.pages) > MAX_PDF_PAGES:
            raise AdapterFrameworkError("CONTENT_TOO_LARGE", "PDF_PAGES")
        parts = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            raise AdapterFrameworkError("REVIEW_REQUIRED", "PDF_IMAGE_ONLY")
        return text
    except ImportError as exc:
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", "pypdf_missing") from exc
    except AdapterFrameworkError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AdapterFrameworkError("PARSING_FAILED", type(exc).__name__) from exc


def extract_jats_xml(body: bytes) -> str:
    """Parse JATS-like XML with entity expansion disabled; return article text."""
    if len(body) > MAX_CONTENT_BYTES:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", str(len(body)))
    head = body[:4000].lower()
    if b"<!entity" in head or (b"<!doctype" in head and b"system" in head):
        raise AdapterFrameworkError("PARSING_FAILED", "XML_ENTITY_FORBIDDEN")
    # Expansion bomb heuristic: huge repeated entity-like patterns
    if body.count(b"&") > 50_000:
        raise AdapterFrameworkError("CONTENT_TOO_LARGE", "XML_ENTITY_EXPANSION")
    try:
        root = ET.fromstring(body)
    except ParseError as exc:
        raise AdapterFrameworkError("PARSING_FAILED", "MALFORMED_XML") from exc
    texts = [t.strip() for t in root.itertext() if t and t.strip()]
    joined = "\n".join(texts)
    joined = re.sub(r"(?i)ignore previous instructions", "[REDACTED_INJECTION]", joined)
    if not joined:
        raise AdapterFrameworkError("EXTRACTION_FAILED", "EMPTY_JATS")
    return joined


class PdfTextAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=PDF_ADAPTER_ID,
            adapter_version=PDF_ADAPTER_VERSION,
            mode="PDF_TEXT",
            capabilities=(
                "FETCH",
                "EXTRACTION",
                "CONTENT_TYPES",
                "ATTACHMENT_HANDLING",
            ),
        )

    def fetch_fixture(
        self,
        *,
        request_id: str,
        url: str,
        transport: FixtureTransport,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
    ) -> FetchEnvelope:
        assert_source_governance_allows_controlled_use(governance)
        resp = transport(url)
        ctype = (resp.content_type or "").split(";", 1)[0].strip().lower()
        body = resp.body or b""
        if (
            ctype not in {"application/pdf", "application/octet-stream"}
            and b"%PDF" not in body[:8]
            and b"%SEDI_PDF_TEXT_FIXTURE%" not in body
            and b"%SEDI_PDF_IMAGE_ONLY_FIXTURE%" not in body
        ):
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", ctype or "missing")
        env = build_fetch_envelope(
            request_id=request_id,
            adapter_id=PDF_ADAPTER_ID,
            adapter_version=PDF_ADAPTER_VERSION,
            url=url,
            response=resp,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )
        if env.error_category:
            return env
        extract_pdf_text(env.body)
        return env

    def fetch_live(
        self,
        *,
        request_id: str,
        url: str,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        allowed_url_patterns: Optional[Sequence[str]] = None,
        trust_level: str = "official",
        review_required: bool = True,
        http_get: Optional[HttpGet] = None,
    ) -> FetchEnvelope:
        env = fetch_live_envelope(
            request_id=request_id,
            url=url,
            governance=governance,
            adapter_id=PDF_ADAPTER_ID,
            adapter_version=PDF_ADAPTER_VERSION,
            max_bytes=max_bytes,
            timeout=timeout,
            allowed_url_patterns=allowed_url_patterns,
            trust_level=trust_level,
            review_required=review_required,
            http_get=http_get,
        )
        if env.error_category:
            return env
        extract_pdf_text(env.body)
        return env


class JatsXmlAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id=JATS_ADAPTER_ID,
            adapter_version=JATS_ADAPTER_VERSION,
            mode="OFFICIAL_XML",
            capabilities=("FETCH", "EXTRACTION", "CONTENT_TYPES"),
        )

    def fetch_fixture(
        self,
        *,
        request_id: str,
        url: str,
        transport: FixtureTransport,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
    ) -> FetchEnvelope:
        assert_source_governance_allows_controlled_use(governance)
        resp = transport(url)
        ctype = (resp.content_type or "").split(";", 1)[0].strip().lower()
        body = resp.body or b""
        if ctype not in {"application/xml", "text/xml", "application/jats+xml"} and not body.lstrip().startswith(
            b"<"
        ):
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", ctype or "missing")
        env = build_fetch_envelope(
            request_id=request_id,
            adapter_id=JATS_ADAPTER_ID,
            adapter_version=JATS_ADAPTER_VERSION,
            url=url,
            response=resp,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )
        if env.error_category:
            return env
        extract_jats_xml(env.body)
        return env

    def fetch_live(
        self,
        *,
        request_id: str,
        url: str,
        governance: SourceGovernanceSnapshot,
        max_bytes: int = MAX_CONTENT_BYTES,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        allowed_url_patterns: Optional[Sequence[str]] = None,
        trust_level: str = "official",
        review_required: bool = True,
        http_get: Optional[HttpGet] = None,
    ) -> FetchEnvelope:
        env = fetch_live_envelope(
            request_id=request_id,
            url=url,
            governance=governance,
            adapter_id=JATS_ADAPTER_ID,
            adapter_version=JATS_ADAPTER_VERSION,
            max_bytes=max_bytes,
            timeout=timeout,
            allowed_url_patterns=allowed_url_patterns,
            trust_level=trust_level,
            review_required=review_required,
            http_get=http_get,
        )
        if env.error_category:
            return env
        extract_jats_xml(env.body)
        return env
