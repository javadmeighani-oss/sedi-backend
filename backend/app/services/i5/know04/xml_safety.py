"""XML safety helpers — XXE / oversized / malformed XML fail closed."""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element, ParseError, fromstring

from backend.app.services.i5.know04.http_client import ConnectorHttpError

_ENTITY = re.compile(rb"<!ENTITY", re.I)
_DOCTYPE_INTERNAL_SUBSET = re.compile(rb"<!DOCTYPE[^>\[]*\[", re.I)
_EXTERNAL_DOCTYPE = re.compile(
    rb"<!DOCTYPE\s+[\w:.-]+\s+(?:PUBLIC\s+\"[^\"]+\"(?:\s+\"[^\"]+\")?|SYSTEM\s+\"[^\"]+\")\s*>",
    re.I,
)


def safe_parse_xml(content: bytes, *, max_bytes: int = 2_097_152) -> Element:
    if len(content) > max_bytes:
        raise ConnectorHttpError("CONTENT_TOO_LARGE", str(len(content)))
    if _ENTITY.search(content) or _DOCTYPE_INTERNAL_SUBSET.search(content):
        raise ConnectorHttpError("XXE_ATTEMPT_BLOCKED", "ENTITY_OR_INTERNAL_DTD")
    # NCBI/NLM E-utilities emit an external PUBLIC/SYSTEM DOCTYPE. Strip it so the
    # DTD is never fetched; ElementTree still does not resolve external entities.
    cleaned = _EXTERNAL_DOCTYPE.sub(b"", content, count=1)
    if re.search(rb"<!DOCTYPE", cleaned, re.I):
        raise ConnectorHttpError("XXE_ATTEMPT_BLOCKED", "<!DOCTYPE")
    try:
        return fromstring(cleaned)
    except ParseError as e:
        raise ConnectorHttpError("MALFORMED_XML", str(e)) from e
