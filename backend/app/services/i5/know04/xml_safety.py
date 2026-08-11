"""XML safety helpers — XXE / oversized / malformed XML fail closed."""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element, ParseError, fromstring

from backend.app.services.i5.know04.http_client import ConnectorHttpError

_XXE_PATTERNS = (
    re.compile(rb"<!ENTITY", re.I),
    re.compile(rb"SYSTEM\s+[\"']", re.I),
    re.compile(rb"<!DOCTYPE", re.I),
)


def safe_parse_xml(content: bytes, *, max_bytes: int = 2_097_152) -> Element:
    if len(content) > max_bytes:
        raise ConnectorHttpError("CONTENT_TOO_LARGE", str(len(content)))
    for pat in _XXE_PATTERNS:
        if pat.search(content):
            raise ConnectorHttpError("XXE_ATTEMPT_BLOCKED", pat.pattern.decode("utf-8", errors="replace"))
    try:
        # ElementTree fromstring does not resolve external entities by default in CPython,
        # but we still reject DOCTYPE/ENTITY defensively.
        return fromstring(content)
    except ParseError as e:
        raise ConnectorHttpError("MALFORMED_XML", str(e)) from e
