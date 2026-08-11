"""PDF text + JATS XML adapter foundations (fixture-driven; fail-closed security)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional
from xml.etree.ElementTree import ParseError

from backend.app.schemas.i5_adapters import AdapterMetadata, FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5.adapters.base import (
    MAX_CONTENT_BYTES,
    AdapterFrameworkError,
    FixtureTransport,
    SourceAdapter,
    assert_source_governance_allows_controlled_use,
    build_fetch_envelope,
)


def extract_pdf_text(body: bytes) -> str:
    """Best-effort PDF text extraction.

    Prefer pypdf when installed; otherwise accept controlled fixtures that embed
    plain text after a %SEDI_PDF_TEXT_FIXTURE% marker (CI-safe).
    """
    if b"%SEDI_PDF_TEXT_FIXTURE%" in body:
        return body.split(b"%SEDI_PDF_TEXT_FIXTURE%", 1)[1].decode("utf-8", errors="replace").strip()
    try:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(body))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            raise AdapterFrameworkError("PARSING_FAILED", "EMPTY_PDF_TEXT")
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
    # Block classic XXE patterns early
    head = body[:4000].lower()
    if b"<!entity" in head or b"<!doctype" in head and b"system" in head:
        raise AdapterFrameworkError("PARSING_FAILED", "XML_ENTITY_FORBIDDEN")
    try:
        # ElementTree does not resolve external entities by default in modern Python
        root = ET.fromstring(body)
    except ParseError as exc:
        raise AdapterFrameworkError("PARSING_FAILED", "MALFORMED_XML") from exc
    texts = [t.strip() for t in root.itertext() if t and t.strip()]
    joined = "\n".join(texts)
    # Prompt-injection marker scrub (source text is untrusted evidence)
    joined = re.sub(r"(?i)ignore previous instructions", "[REDACTED_INJECTION]", joined)
    if not joined:
        raise AdapterFrameworkError("EXTRACTION_FAILED", "EMPTY_JATS")
    return joined


class PdfTextAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id="i5.pdf_text",
            adapter_version="know01-v1",
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
        ):
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", ctype or "missing")
        env = build_fetch_envelope(
            request_id=request_id,
            adapter_id="i5.pdf_text",
            adapter_version="know01-v1",
            url=url,
            response=resp,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )
        if env.error_category:
            return env
        extract_pdf_text(env.body)
        return env


class JatsXmlAdapter(SourceAdapter):
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            adapter_id="i5.jats_xml",
            adapter_version="know01-v1",
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
        if ctype not in {"application/xml", "text/xml", "application/jats+xml"} and not body.lstrip().startswith(b"<"):
            raise AdapterFrameworkError("INVALID_CONTENT_TYPE", ctype or "missing")
        env = build_fetch_envelope(
            request_id=request_id,
            adapter_id="i5.jats_xml",
            adapter_version="know01-v1",
            url=url,
            response=resp,
            max_bytes=max_bytes,
            allowed_domain=governance.allowed_domain,
        )
        if env.error_category:
            return env
        extract_jats_xml(env.body)
        return env
