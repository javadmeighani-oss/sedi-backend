"""Safe content parsing for curated KB fetch (Gate 3G)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional

_SKIP_TAGS = frozenset({"script", "style", "noscript"})
_STRIP_TAGS = frozenset({"nav", "header", "footer", "aside"})

HTML_MIN_TEXT_LENGTH = 400

_NAV_PHRASES = (
    "skip to main content",
    "search the nhs website",
    "search the website",
    "health a to z",
    "nhs services",
    "support links",
    "accessibility statement",
    "crown copyright",
    "our policies",
    "browse more",
    "back to healthy living",
    "profile editor login",
    "report an issue with the nhs website",
    "find my nhs number",
    "view your test results",
    "healthcare abroad",
    "other nhs websites",
)

_NOISE = re.compile(
    r"(cookie|privacy policy|subscribe|newsletter|all rights reserved|accept cookies)",
    re.I,
)

_CONTAINER_SPECS: list[dict[str, str]] = [
    {"tag": "article"},
    {"tag": "main"},
    {"role": "main"},
    {"id_": "maincontent"},
    {"class_substr": "nhsuk-main-wrapper"},
    {"class_substr": "nhsuk-grid-column-two-thirds"},
]


@dataclass
class ParsedContent:
    title: str
    text: str
    content_type: str
    parser_type: str
    content_hash: str
    parse_findings: List[Dict[str, Any]] = field(default_factory=list)
    extraction_container: str = ""


class _RegionExtractor(HTMLParser):
    """Extract visible text from a semantic HTML region."""

    def __init__(
        self,
        *,
        mode: str = "container",
        match_tag: Optional[str] = None,
        match_id: Optional[str] = None,
        match_class_substr: Optional[str] = None,
        match_role: Optional[str] = None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.mode = mode
        self.match_tag = match_tag
        self.match_id = match_id
        self.match_class_substr = match_class_substr
        self.match_role = match_role
        self.parts: list[str] = []
        self._capture_depth = 0
        self._suppress_depth = 0
        self._body_started = False

    def _attrs(self, attrs) -> dict[str, str]:
        return {k.lower(): (v or "") for k, v in attrs}

    def _matches(self, tag: str, attrs: dict[str, str]) -> bool:
        if self.match_tag and tag != self.match_tag:
            return False
        if self.match_id and attrs.get("id") != self.match_id:
            return False
        if self.match_role and attrs.get("role") != self.match_role:
            return False
        if self.match_class_substr and self.match_class_substr not in attrs.get("class", ""):
            return False
        return any((self.match_tag, self.match_id, self.match_role, self.match_class_substr))

    def _enter_suppress(self) -> None:
        self._suppress_depth += 1

    def _leave_suppress(self) -> None:
        if self._suppress_depth > 0:
            self._suppress_depth -= 1

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        ad = self._attrs(attrs)
        if t in _SKIP_TAGS or t in _STRIP_TAGS:
            if self._capture_depth > 0 or (self.mode == "body_fallback" and self._body_started):
                self._enter_suppress()
            return
        if self._suppress_depth > 0:
            return

        if self.mode == "body_fallback":
            if t == "body":
                self._body_started = True
                self._capture_depth = 1
            elif self._body_started and self._capture_depth > 0:
                self._capture_depth += 1
            return

        if self._capture_depth > 0:
            self._capture_depth += 1
            return
        if self._matches(t, ad):
            self._capture_depth = 1

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in _SKIP_TAGS or t in _STRIP_TAGS:
            self._leave_suppress()
            return
        if self._suppress_depth > 0:
            return
        if self._capture_depth > 0:
            self._capture_depth -= 1

    def handle_data(self, data):
        if self._suppress_depth == 0 and self._capture_depth > 0 and data:
            self.parts.append(data)


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _container_label(spec: dict[str, str]) -> str:
    if "tag" in spec:
        return spec["tag"]
    if "role" in spec:
        return f'role={spec["role"]}'
    if "id_" in spec:
        return f'#{spec["id_"]}'
    if "class_substr" in spec:
        return f'.{spec["class_substr"]}'
    return "unknown"


def _extract_region(html: str, **spec: str) -> str:
    kwargs: dict[str, Any] = {"mode": "container"}
    if "tag" in spec:
        kwargs["match_tag"] = spec["tag"]
    if "id_" in spec:
        kwargs["match_id"] = spec["id_"]
    if "class_substr" in spec:
        kwargs["match_class_substr"] = spec["class_substr"]
    if "role" in spec:
        kwargs["match_role"] = spec["role"]
    extractor = _RegionExtractor(**kwargs)
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:
        return ""
    return _normalize_ws(" ".join(extractor.parts))


def _extract_body_fallback(html: str) -> str:
    extractor = _RegionExtractor(mode="body_fallback")
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:
        return ""
    return _normalize_ws(" ".join(extractor.parts))


def extract_semantic_html_text(html: str) -> tuple[str, str]:
    """Return (text, container_label) using semantic container priority."""
    for spec in _CONTAINER_SPECS:
        text = _extract_region(html, **spec)
        if text:
            return text, _container_label(spec)
    text = _extract_body_fallback(html)
    if text:
        return text, "body"
    return "", "none"


def _substantive_sentence_count(text: str) -> int:
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    return sum(1 for s in sentences if len(s.split()) >= 10)


def is_hub_page_thin(text: str) -> bool:
    """Detect hub/listing pages with teaser text and link titles but little guidance."""
    if len(text) >= HTML_MIN_TEXT_LENGTH:
        return False
    if _substantive_sentence_count(text) >= 2:
        return False
    words = text.split()
    if len(words) <= 80 and _substantive_sentence_count(text) < 2:
        return True
    return len(text) < HTML_MIN_TEXT_LENGTH and _substantive_sentence_count(text) < 1


def is_nav_heavy(text: str) -> bool:
    norm = text.lower()
    hits = sum(1 for phrase in _NAV_PHRASES if phrase in norm)
    if hits >= 3:
        return True
    if hits >= 2 and len(text) < 800:
        return True
    nav_chars = sum(len(phrase) for phrase in _NAV_PHRASES if phrase in norm)
    return nav_chars > len(text) * 0.22


def validate_html_extracted_text(text: str, *, html_min_text_length: int = HTML_MIN_TEXT_LENGTH) -> None:
    """Raise ValueError with parse_* codes when HTML extraction is not KB-useful."""
    cleaned = _normalize_ws(text)
    if not cleaned:
        raise ValueError("parse_no_useful_main_content")
    if len(cleaned) < html_min_text_length:
        if is_hub_page_thin(cleaned):
            raise ValueError("parse_hub_page_thin")
        raise ValueError("parse_too_short")
    if is_nav_heavy(cleaned):
        raise ValueError("parse_nav_heavy")
    if is_hub_page_thin(cleaned):
        raise ValueError("parse_hub_page_thin")


def parse_content(
    raw: bytes,
    content_type: str,
    *,
    title_hint: Optional[str] = None,
    min_text_length: int = 80,
    html_min_text_length: int = HTML_MIN_TEXT_LENGTH,
) -> ParsedContent:
    ctype_raw = content_type if isinstance(content_type, str) else str(content_type or "")
    ctype = ctype_raw.split(";")[0].strip().lower()
    if ctype == "application/pdf":
        return ParsedContent(
            title=title_hint or "PDF document",
            text="",
            content_type=ctype,
            parser_type="unsupported_pdf",
            content_hash=content_hash(raw[:4096].hex()),
        )

    text_body = raw.decode("utf-8", errors="replace").lstrip("\ufeff")
    parser_type = "text"
    title = title_hint or ""
    extraction_container = ""
    parse_findings: list[dict[str, Any]] = []

    if ctype in ("text/html", "application/xhtml+xml") or "<html" in text_body.lower():
        parser_type = "html"
        text_body, extraction_container = extract_semantic_html_text(text_body)
        m = re.search(r"<title[^>]*>(.*?)</title>", raw.decode("utf-8", errors="replace"), re.I | re.S)
        if m and not title:
            title = _normalize_ws(re.sub(r"<[^>]+>", " ", m.group(1)))
        validate_html_extracted_text(text_body, html_min_text_length=html_min_text_length)
    else:
        text_body = _normalize_ws(text_body)
        if len(text_body) < min_text_length:
            raise ValueError("parse_too_short")
        if _NOISE.search(text_body[:500]) and len(text_body) < 400:
            raise ValueError("parse_mostly_noise")

    text_body = _normalize_ws(text_body)
    return ParsedContent(
        title=title or "Untitled",
        text=text_body,
        content_type=ctype or "text/plain",
        parser_type=parser_type,
        content_hash=content_hash(text_body),
        parse_findings=parse_findings,
        extraction_container=extraction_container,
    )
