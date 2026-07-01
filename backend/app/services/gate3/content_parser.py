"""Safe content parsing for curated KB fetch (Gate 3G)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Optional


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = False
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip and data:
            self.parts.append(data)


@dataclass
class ParsedContent:
    title: str
    text: str
    content_type: str
    parser_type: str
    content_hash: str


_NOISE = re.compile(
    r"(cookie|privacy policy|subscribe|newsletter|all rights reserved|accept cookies)",
    re.I,
)


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def parse_content(
    raw: bytes,
    content_type: str,
    *,
    title_hint: Optional[str] = None,
    min_text_length: int = 80,
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

    text_body = raw.decode("utf-8", errors="replace")
    parser_type = "text"
    title = title_hint or ""

    if ctype in ("text/html", "application/xhtml+xml") or "<html" in text_body.lower():
        parser_type = "html"
        extractor = _TextExtractor()
        extractor.feed(text_body)
        text_body = " ".join(extractor.parts)
        m = re.search(r"<title[^>]*>(.*?)</title>", raw.decode("utf-8", errors="replace"), re.I | re.S)
        if m and not title:
            title = re.sub(r"\s+", " ", m.group(1)).strip()

    text_body = re.sub(r"\s+", " ", text_body).strip()
    if len(text_body) < min_text_length:
        raise ValueError("parse_too_short")
    if _NOISE.search(text_body[:500]) and len(text_body) < 400:
        raise ValueError("parse_mostly_noise")

    return ParsedContent(
        title=title or "Untitled",
        text=text_body,
        content_type=ctype or "text/plain",
        parser_type=parser_type,
        content_hash=content_hash(text_body),
    )
