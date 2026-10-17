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

EXTRACTOR_VERSION = "w3p01-conceptual-1.0.3"


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


# --- Section-level extraction (one candidate per content section of a page) -------------

SECTION_EXTRACTOR_VERSION = "w3p01-conceptual-sections-1.0.0"
MAX_SECTIONS_PER_DOCUMENT = 16
MIN_SECTION_TEXT_CHARS = 160
MAX_SECTION_STATEMENT_CHARS = 1400
# Share of section text that sits inside links; above this the section is a link list.
MAX_SECTION_LINK_TEXT_RATIO = 0.45

# Chrome containers. Not "form"/"button": some sites wrap whole pages in a <form> and
# leave <button> unclosed, which would silence the entire document.
_SECTION_SKIP_TAGS = frozenset(
    {"script", "style", "noscript", "nav", "header", "footer", "aside", "svg", "template", "iframe"}
)
_SECTION_HEADING_TAGS = frozenset({"h1", "h2", "h3"})
# Boilerplate sections are dropped entirely.
_BOILERPLATE_SECTION_HEADINGS = re.compile(
    r"^(?:(?:related(?: health topics| issues| links| pages| resources)?|references?|sources"
    r"|more information|learn more|clinical trials?|journal articles|find an expert"
    r"|(?:additional |other |federal )?resources|see also|share(?: this page)?|connect with \w+"
    r"|contact(?: us)?|en español|español|page last reviewed.*|next review due.*|start here"
    r"|reprints?|patient handouts|multimedia|topic image|medical encyclopedia|disclaimers?"
    r"|footnotes|acknowledg(?:e)?ments?|newsletters?|subscribe.*|citations?|for more information.*"
    r"|where can i (?:learn|find) more.*|additional (?:federal )?(?:resources|information).*"
    r"|explore clinical trials.*|why is \w+ studying.*|how is \w+ research.*"
    r"|statistics and research|book traversal links.*|support links|find out more"
    # Agency self-description (CDC/NIH "What CDC is doing", "About us"): administrative text that
    # outranked real guidance for questions such as "how much exercise".
    r"|what (?:cdc|nih|nci|nhs|who|\w+) (?:is|are) doing.*|how (?:cdc|nih|nci|\w+) (?:is )?helps?.*"
    r"|about us|our work|our partners|partners(?: and .*)?|funding(?: opportunities)?"
    # Country-specific triage boxes (e.g. NHS 111 / 999 / "see a GP"): emergency and
    # escalation guidance is owned by I4 and must not be served from foreign knowledge.
    r"|(?:non-)?urgent advice.*|immediate action required.*|important: get urgent help.*"
    r"|help and support(?: for .*)?|video: .*)\s*[:?.]?\s*)$",
    re.IGNORECASE,
)
# Page widgets whose heading carries no meaning; their text continues the page introduction.
_WIDGET_SECTION_HEADINGS = re.compile(
    r"^(?:language switcher|on this page|in this section|quick links|contents|print(?: this page)?)\s*:?\s*$",
    re.IGNORECASE,
)
_BOILERPLATE_INTRO_PREFIXES = ("download pdf", "print ", "share ", "en español")
_LANGUAGE_SWITCHER_PREFIX = re.compile(r"^(?:English\s+Español\s+|Español\s+English\s+)", re.IGNORECASE)


class _SectionExtractor(HTMLParser):
    """Collect (level, heading, text, link_text_chars) sections from page content."""

    def __init__(self, *, main_only: bool) -> None:
        super().__init__(convert_charrefs=True)
        self._main_only = main_only
        self._main_depth = 0
        self._skip: list[str] = []
        self._anchor = 0
        self._heading: Optional[str] = None
        self._heading_buf: list[str] = []
        self._in_title = False
        self.title = ""
        self.h1 = ""
        self.sections: list[dict] = []
        self._h1_index: Optional[int] = None

    def _recording(self) -> bool:
        return not self._skip and (not self._main_only or self._main_depth > 0)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "main":
            self._main_depth += 1
        if tag in _SECTION_SKIP_TAGS:
            self._skip.append(tag)
        if tag == "title":
            self._in_title = True
        if tag == "a":
            self._anchor += 1
        if tag in _SECTION_HEADING_TAGS and self._recording():
            self._heading = tag
            self._heading_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "main" and self._main_depth:
            self._main_depth -= 1
        if tag in _SECTION_SKIP_TAGS and tag in self._skip:
            # Pop the innermost matching container (tolerates sloppy nesting).
            idx = len(self._skip) - 1 - self._skip[::-1].index(tag)
            del self._skip[idx:]
        if tag == "title":
            self._in_title = False
        if tag == "a" and self._anchor:
            self._anchor -= 1
        if self._heading is not None and tag == self._heading:
            text = " ".join(" ".join(self._heading_buf).split())
            if self._heading == "h1":
                if not self.h1 and text:
                    self.h1 = text
                    self._h1_index = len(self.sections)
            elif text:
                self.sections.append(
                    {"level": int(self._heading[1]), "heading": text, "parts": [], "link_chars": 0}
                )
            self._heading = None
            self._heading_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
            return
        if not self._recording():
            return
        text = data.strip()
        if not text:
            return
        if self._heading is not None:
            self._heading_buf.append(text)
            return
        if not self.sections or (self._h1_index is not None and len(self.sections) == self._h1_index):
            # Text between the H1 and the first section heading → page introduction.
            self.sections.append({"level": 2, "heading": "", "parts": [], "link_chars": 0})
        section = self.sections[-1]
        section["parts"].append(text)
        if self._anchor:
            section["link_chars"] += len(text)

    def content_sections(self) -> list[dict]:
        start = self._h1_index or 0
        return self.sections[start:]


def _page_title(parser: _SectionExtractor) -> str:
    if parser.h1:
        return parser.h1
    raw = " ".join(parser.title.split())
    return re.split(r"\s+[|\-–]\s+", raw)[0].strip() if raw else ""


def _section_key(level: int, heading: str, seen: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", heading.casefold()).strip("-")[:80]
    if not slug:
        slug = "intro" if not heading else sha256_hex(heading.encode("utf-8"))[:12]
    key = f"h{level}:{slug}"
    n = 2
    while key in seen:
        key = f"h{level}:{slug}-{n}"
        n += 1
    seen.add(key)
    return key


def _bounded_statement(prefix: str, text: str) -> str:
    statement = f"{prefix}{text}"
    if len(statement) <= MAX_SECTION_STATEMENT_CHARS:
        return statement
    cut = statement[:MAX_SECTION_STATEMENT_CHARS]
    end = cut.rfind(". ")
    return cut[: end + 1] if end >= MAX_SECTION_STATEMENT_CHARS // 2 else cut


def extract_sections_from_html(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    """One candidate per narrative content section; empty when the page has no usable sections.

    Navigation/header/footer chrome, link-list sections and boilerplate headings are dropped.
    Each statement carries the page title and section heading, so a section is
    self-describing for eligibility and retrieval.
    """
    from backend.app.services.i5.governed_specialized_entity_eligibility import (
        statement_dominated_by_nav_chrome,
    )

    html = envelope.body.decode(envelope.charset or "utf-8", errors="replace")
    parser = _SectionExtractor(main_only=bool(re.search(r"<main[\s>]", html, re.IGNORECASE)))
    try:
        parser.feed(html)
    except Exception as exc:  # noqa: BLE001 — map to taxonomy
        raise AdapterFrameworkError("PARSING_FAILED", type(exc).__name__) from exc
    title = _page_title(parser)
    seen: set[str] = set()
    out: list[ExtractionCandidate] = []
    for section in parser.content_sections():
        heading = section["heading"]
        if heading and _BOILERPLATE_SECTION_HEADINGS.match(heading):
            continue
        if heading and _WIDGET_SECTION_HEADINGS.match(heading):
            heading = ""
        text = " ".join(" ".join(section["parts"]).split())
        text = _LANGUAGE_SWITCHER_PREFIX.sub("", text)
        if len(text) < MIN_SECTION_TEXT_CHARS:
            continue
        if not heading and text.casefold().startswith(_BOILERPLATE_INTRO_PREFIXES):
            continue
        if section["link_chars"] / max(len(text), 1) > MAX_SECTION_LINK_TEXT_RATIO:
            continue
        if statement_dominated_by_nav_chrome(text[:520]):
            continue
        key = _section_key(section["level"], heading, seen)
        if title and heading:
            prefix = f"{title} — {heading}: "
        elif title:
            prefix = f"{title}: "
        else:
            prefix = f"{heading}: " if heading else ""
        out.append(
            ExtractionCandidate(
                title=title or "html-document",
                normalized_text=canonicalize_text(text),
                language="en",
                source_location=f"{envelope.canonical_url}#{key}",
                content_hash=sha256_hex(canonicalize_text(text).encode("utf-8")),
                extractor_version=SECTION_EXTRACTOR_VERSION,
                extraction_confidence=0.6,
                warnings=("candidate_only_not_approved_knowledge", "section"),
                section_anchor=key,
                claim_candidate=_bounded_statement(prefix, text),
            )
        )
        if len(out) >= MAX_SECTIONS_PER_DOCUMENT:
            break
    return tuple(out)


def extract_from_html(envelope: FetchEnvelope) -> tuple[ExtractionCandidate, ...]:
    if envelope.error_category is not None:
        raise AdapterFrameworkError("EXTRACTION_FAILED", envelope.error_category)
    if envelope.content_type not in {"text/html", "application/xhtml+xml"}:
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", envelope.content_type)
    sections = extract_sections_from_html(envelope)
    if sections:
        return sections
    # No usable sections (e.g. heading-less page): single document-level claim window.
    parser = _TextExtractor()
    try:
        parser.feed(envelope.body.decode(envelope.charset or "utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 — map to taxonomy
        raise AdapterFrameworkError("PARSING_FAILED", type(exc).__name__) from exc
    text = parser.text()
    # Bounded chrome self-heal (Format Resilience compatible; no parser redesign).
    from backend.app.services.i5.governed_specialized_entity_eligibility import (
        select_clinical_claim_window,
        statement_dominated_by_nav_chrome,
        strip_html_nav_chrome,
    )

    text = strip_html_nav_chrome(text)
    if len(canonicalize_text(text)) < 20:
        raise AdapterFrameworkError("EXTRACTION_FAILED", "too_short")
    claim_src = select_clinical_claim_window(
        canonicalize_text(text),
        canonical_url=envelope.canonical_url,
    )
    # Fail closed: never ship a chrome-dominated claim_candidate for KU statements.
    if not claim_src or statement_dominated_by_nav_chrome(claim_src):
        raise AdapterFrameworkError("EXTRACTION_FAILED", "no_clean_claim")
    claim = claim_src[:520]
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
