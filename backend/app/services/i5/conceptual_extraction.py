"""I5-IMPL-W3-P01 — conceptual extraction to candidates (not approved knowledge)."""
from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Optional
from xml.etree import ElementTree as ET

from backend.app.schemas.i5_adapters import ExtractionCandidate, FetchEnvelope
from backend.app.services.i5.adapters.base import AdapterFrameworkError, sha256_hex
from backend.app.services.i5.normalization import canonicalize_text

EXTRACTOR_VERSION = "w3p01-conceptual-1.0.2"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title += data
            return
        text = data.strip()
        if text:
            self._parts.append(text)

    def text(self) -> str:
        return " ".join(self._parts)


def _candidate(
    *,
    title: str,
    text: str,
    source_location: str,
    language: str = "en",
    confidence: float = 0.5,
    warnings: tuple[str, ...] = (),
    claim: Optional[str] = None,
) -> ExtractionCandidate:
    canonical = canonicalize_text(text)
    if not canonical:
        raise AdapterFrameworkError("EXTRACTION_FAILED", "empty")
    return ExtractionCandidate(
        title=title.strip() or "untitled",
        normalized_text=canonical,
        language=language,
        source_location=source_location,
        content_hash=sha256_hex(canonical.encode("utf-8")),
        extractor_version=EXTRACTOR_VERSION,
        extraction_confidence=confidence,
        warnings=warnings,
        claim_candidate=claim,
    )


def extract_from_html(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    if envelope.error_category is not None:
        raise AdapterFrameworkError("EXTRACTION_FAILED", envelope.error_category)
    if envelope.content_type not in {"text/html", "application/xhtml+xml"}:
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", envelope.content_type)
    parser = _TextExtractor()
    try:
        parser.feed(envelope.body.decode(envelope.charset or "utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 — map to taxonomy
        raise AdapterFrameworkError("PARSING_FAILED", type(exc).__name__) from exc
    text = parser.text()
    # Bounded chrome self-heal (Format Resilience compatible; no parser redesign).
    from backend.app.services.i5.governed_specialized_entity_eligibility import (
        select_clinical_claim_window,
        strip_html_nav_chrome,
    )

    text = strip_html_nav_chrome(text)
    if len(canonicalize_text(text)) < 20:
        raise AdapterFrameworkError("EXTRACTION_FAILED", "too_short")
    claim_src = select_clinical_claim_window(
        canonicalize_text(text),
        canonical_url=envelope.canonical_url,
    )
    claim = claim_src[:520] if claim_src else None
    return (
        _candidate(
            title=parser.title or "html-document",
            text=text,
            source_location=envelope.canonical_url,
            confidence=0.55,
            warnings=("candidate_only_not_approved_knowledge",),
            claim=claim,
        ),
    )


def extract_from_json_api(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    if envelope.error_category is not None:
        raise AdapterFrameworkError("EXTRACTION_FAILED", envelope.error_category)
    if envelope.content_type not in {"application/json", "application/vnd.api+json"}:
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", envelope.content_type)
    try:
        payload = json.loads(envelope.body.decode(envelope.charset or "utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AdapterFrameworkError("PARSING_FAILED", type(exc).__name__) from exc
    if not isinstance(payload, dict):
        raise AdapterFrameworkError("EXTRACTION_FAILED", "non_object")
    title = str(payload.get("title") or payload.get("name") or "api-document")
    text = str(payload.get("text") or payload.get("summary") or payload.get("content") or "")
    if not text.strip():
        raise AdapterFrameworkError("EXTRACTION_FAILED", "missing_text")
    return (
        _candidate(
            title=title,
            text=text,
            source_location=envelope.canonical_url,
            confidence=0.6,
            warnings=("candidate_only_not_approved_knowledge",),
            claim=canonicalize_text(text)[:240] or None,
        ),
    )


def extract_from_rss(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    if envelope.error_category is not None:
        raise AdapterFrameworkError("EXTRACTION_FAILED", envelope.error_category)
    if envelope.content_type not in {
        "application/rss+xml",
        "application/atom+xml",
        "application/xml",
        "text/xml",
    }:
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", envelope.content_type)
    try:
        root = ET.fromstring(envelope.body.decode(envelope.charset or "utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        raise AdapterFrameworkError("PARSING_FAILED", type(exc).__name__) from exc
    items: list[ExtractionCandidate] = []
    # RSS item / Atom entry
    for node in list(root.iter()):
        tag = re.sub(r"^\{.*\}", "", node.tag).lower()
        if tag not in {"item", "entry"}:
            continue
        title = ""
        summary = ""
        link = envelope.canonical_url
        for child in list(node):
            ctag = re.sub(r"^\{.*\}", "", child.tag).lower()
            if ctag == "title" and child.text:
                title = child.text
            elif ctag in {"description", "summary", "content"} and (child.text or "").strip():
                summary = child.text or ""
            elif ctag == "link":
                href = child.attrib.get("href") or (child.text or "")
                if href.strip():
                    link = href.strip()
        if not summary.strip():
            continue
        items.append(
            _candidate(
                title=title or "feed-item",
                text=summary,
                source_location=link,
                confidence=0.5,
                warnings=("candidate_only_not_approved_knowledge", "feed_item"),
                claim=canonicalize_text(summary)[:240] or None,
            )
        )
    if not items:
        raise AdapterFrameworkError("EXTRACTION_FAILED", "no_items")
    return tuple(items)


def extract_from_jats(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    from backend.app.services.i5.adapters.pdf_jats import extract_jats_xml

    if envelope.error_category is not None:
        raise AdapterFrameworkError("EXTRACTION_FAILED", envelope.error_category)
    text = extract_jats_xml(envelope.body)
    return (
        _candidate(
            title="jats-document",
            text=text,
            source_location=envelope.canonical_url,
            confidence=0.65,
            warnings=("candidate_only_not_approved_knowledge", "jats"),
            claim=canonicalize_text(text)[:240] or None,
        ),
    )


def extract_from_pdf(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    from backend.app.services.i5.adapters.pdf_jats import extract_pdf_text

    if envelope.error_category is not None:
        raise AdapterFrameworkError("EXTRACTION_FAILED", envelope.error_category)
    text = extract_pdf_text(envelope.body)
    return (
        _candidate(
            title="pdf-document",
            text=text,
            source_location=envelope.canonical_url,
            confidence=0.55,
            warnings=("candidate_only_not_approved_knowledge", "pdf_text"),
            claim=canonicalize_text(text)[:240] or None,
        ),
    )


def extract_from_csv_tsv(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    from backend.app.services.i5.adapters.tabular_docx import extract_csv_tsv_text

    if envelope.error_category is not None:
        raise AdapterFrameworkError("EXTRACTION_FAILED", envelope.error_category)
    text = extract_csv_tsv_text(envelope.body)
    return (
        _candidate(
            title="tabular-document",
            text=text,
            source_location=envelope.canonical_url,
            confidence=0.5,
            warnings=("candidate_only_not_approved_knowledge", "csv_tsv"),
            claim=canonicalize_text(text)[:240] or None,
        ),
    )


def extract_from_docx(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    from backend.app.services.i5.adapters.tabular_docx import extract_docx_text

    if envelope.error_category is not None:
        raise AdapterFrameworkError("EXTRACTION_FAILED", envelope.error_category)
    text = extract_docx_text(envelope.body)
    return (
        _candidate(
            title="docx-document",
            text=text,
            source_location=envelope.canonical_url,
            confidence=0.5,
            warnings=("candidate_only_not_approved_knowledge", "docx"),
            claim=canonicalize_text(text)[:240] or None,
        ),
    )


def extract_candidates(envelope: FetchEnvelope, *, mode: str) -> tuple[ExtractionCandidate, ...]:
    """Route extraction by adapter mode. Never marks candidates as approved knowledge."""
    if mode == "PUBLIC_WEB_FETCH":
        return extract_from_html(envelope)
    if mode in {"OFFICIAL_API", "OFFICIAL_JSON"}:
        return extract_from_json_api(envelope)
    if mode == "RSS_OR_FEED":
        return extract_from_rss(envelope)
    if mode == "OFFICIAL_XML":
        return extract_from_jats(envelope)
    if mode == "PDF_TEXT":
        return extract_from_pdf(envelope)
    if mode == "CSV_TSV":
        return extract_from_csv_tsv(envelope)
    if mode == "DOCX":
        return extract_from_docx(envelope)
    raise AdapterFrameworkError("UNSUPPORTED_FORMAT", mode)
