"""Governed representation classification — Content-Type is never sole authority.

Signature / sniff + declared policy + Content-Type must agree when unsafe mismatch.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.app.services.i5.adapters.base import AdapterFrameworkError

REPRESENTATION_CLASSES = frozenset(
    {
        "HTML",
        "JSON",
        "RSS_ATOM",
        "XML_JATS",
        "PDF_TEXT",
        "PDF_IMAGE_ONLY",
        "CSV_TSV",
        "DOCX",
        "UNKNOWN",
    }
)

# Map representation → adapter mode
REPRESENTATION_TO_MODE = {
    "HTML": "PUBLIC_WEB_FETCH",
    "JSON": "OFFICIAL_API",
    "RSS_ATOM": "RSS_OR_FEED",
    "XML_JATS": "OFFICIAL_XML",
    "PDF_TEXT": "PDF_TEXT",
    "PDF_IMAGE_ONLY": "PDF_TEXT",  # detected then fail-closed / review
    "CSV_TSV": "CSV_TSV",
    "DOCX": "DOCX",
}


@dataclass(frozen=True)
class RepresentationDecision:
    representation: str
    adapter_mode: str
    signature: str
    content_type_observed: str
    mime_trusted: bool
    mismatch_fail_closed: bool
    detail: str = ""


def _ctype(content_type: Optional[str]) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def sniff_signature(payload: bytes) -> str:
    """Bounded magic sniff (first 512 bytes). Returns a signature token."""
    head = (payload or b"")[:512]
    stripped = head.lstrip()
    if stripped.startswith(b"%PDF"):
        return "PDF"
    if stripped.startswith(b"PK\x03\x04") or stripped.startswith(b"PK\x05\x06"):
        # OOXML / zip — refine via [Content_Types].xml presence at caller
        return "ZIP_OOXML"
    if stripped.startswith(b"{") or stripped.startswith(b"["):
        return "JSON"
    low = stripped[:400].lower()
    if b"<rss" in low or b"<feed" in low or (b"atom" in low and b"<feed" in low):
        return "RSS_ATOM"
    if b"<!doctype html" in low or b"<html" in low:
        return "HTML"
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<"):
        if b"<article" in low or b"jats" in low or b"xmlns:jats" in low:
            return "XML_JATS"
        if b"<rss" in low or b"<feed" in low:
            return "RSS_ATOM"
        return "XML"
    # Tabular heuristic: printable + delimiters, no nulls
    sample = head[:2048] if len(head) > 2048 else head
    if sample and b"\x00" not in sample:
        try:
            text = sample.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = sample.decode("latin-1")
            except UnicodeDecodeError:
                return "UNKNOWN"
        if "\n" in text or "\r" in text:
            first = text.splitlines()[0] if text.splitlines() else ""
            if first.count(",") >= 1 and not first.lstrip().startswith("<"):
                return "CSV"
            if first.count("\t") >= 1 and not first.lstrip().startswith("<"):
                return "TSV"
    return "UNKNOWN"


def _declared_to_rep(declared: Optional[str]) -> Optional[str]:
    d = (declared or "").strip().upper()
    mapping = {
        "HTML": "HTML",
        "PUBLIC_WEB_FETCH": "HTML",
        "JSON": "JSON",
        "OFFICIAL_API": "JSON",
        "OFFICIAL_JSON": "JSON",
        "RSS": "RSS_ATOM",
        "ATOM": "RSS_ATOM",
        "RSS_OR_FEED": "RSS_ATOM",
        "RSS_ATOM": "RSS_ATOM",
        "XML": "XML_JATS",
        "JATS": "XML_JATS",
        "JATS_XML": "XML_JATS",
        "OFFICIAL_XML": "XML_JATS",
        "XML_JATS": "XML_JATS",
        "PDF": "PDF_TEXT",
        "PDF_TEXT": "PDF_TEXT",
        "PDF_IMAGE_ONLY": "PDF_IMAGE_ONLY",
        "CSV": "CSV_TSV",
        "TSV": "CSV_TSV",
        "CSV_TSV": "CSV_TSV",
        "DOCX": "DOCX",
        "OCR": "UNKNOWN",
        "PDF_SCANNED": "PDF_IMAGE_ONLY",
    }
    return mapping.get(d)


def classify_representation(
    *,
    content_type: Optional[str] = None,
    payload: Optional[bytes] = None,
    filename_hint: Optional[str] = None,
    declared_format: Optional[str] = None,
    allow_mime_only_when_empty_body: bool = True,
) -> RepresentationDecision:
    """Classify into a controlled representation class.

    Content-Type alone is not trusted when body bytes contradict it unsafely.
    """
    ctype = _ctype(content_type)
    body = payload or b""
    sig = sniff_signature(body) if body else "EMPTY"
    name = (filename_hint or "").lower()
    declared_rep = _declared_to_rep(declared_format)

    # Signature-first when body present
    sig_to_rep = {
        "PDF": "PDF_TEXT",
        "JSON": "JSON",
        "RSS_ATOM": "RSS_ATOM",
        "HTML": "HTML",
        "XML_JATS": "XML_JATS",
        "XML": "XML_JATS",
        "CSV": "CSV_TSV",
        "TSV": "CSV_TSV",
        "ZIP_OOXML": "DOCX",  # refined below
    }

    mime_to_rep = {
        "text/html": "HTML",
        "application/xhtml+xml": "HTML",
        "application/json": "JSON",
        "application/vnd.api+json": "JSON",
        "text/json": "JSON",
        "application/rss+xml": "RSS_ATOM",
        "application/atom+xml": "RSS_ATOM",
        "application/feed+json": "RSS_ATOM",
        "application/xml": "XML_JATS",
        "text/xml": "XML_JATS",
        "application/jats+xml": "XML_JATS",
        "application/pdf": "PDF_TEXT",
        "text/csv": "CSV_TSV",
        "application/csv": "CSV_TSV",
        "text/tab-separated-values": "CSV_TSV",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
        "application/msword": "DOCX",
    }

    mime_rep = mime_to_rep.get(ctype)
    sig_rep = sig_to_rep.get(sig)

    # Refine ZIP → DOCX only when OOXML markers present; else UNKNOWN/fail
    if sig == "ZIP_OOXML" and body:
        if b"word/" in body[:8192] or b"[Content_Types].xml" in body[:16384] or name.endswith(".docx"):
            sig_rep = "DOCX"
        else:
            sig_rep = None
            sig = "ZIP_UNSUPPORTED"

    # Filename last resort
    name_rep = None
    if name.endswith((".html", ".htm")):
        name_rep = "HTML"
    elif name.endswith(".json"):
        name_rep = "JSON"
    elif name.endswith((".rss", ".atom")):
        name_rep = "RSS_ATOM"
    elif name.endswith(".xml"):
        name_rep = "XML_JATS"
    elif name.endswith(".pdf"):
        name_rep = "PDF_TEXT"
    elif name.endswith((".csv", ".tsv")):
        name_rep = "CSV_TSV"
    elif name.endswith(".docx"):
        name_rep = "DOCX"

    chosen: Optional[str] = None
    detail = ""
    mismatch = False

    if declared_rep == "PDF_IMAGE_ONLY":
        chosen = "PDF_IMAGE_ONLY"
    elif declared_rep and declared_rep != "UNKNOWN":
        chosen = declared_rep
        # Declared vs signature conflict on unsafe binaries → fail closed
        if sig_rep and sig_rep != declared_rep and {sig_rep, declared_rep} & {"PDF_TEXT", "DOCX", "JSON"}:
            if sig in {"PDF", "ZIP_OOXML", "JSON"} and declared_rep != sig_rep:
                mismatch = True
                detail = f"declared_vs_signature:{declared_rep}:{sig}"
    elif body and sig_rep:
        chosen = sig_rep
        if mime_rep and mime_rep != sig_rep:
            # Unsafe spoof: claim HTML/JSON but body is PDF/DOCX/etc.
            dangerous = {mime_rep, sig_rep}
            if ("PDF_TEXT" in dangerous or "DOCX" in dangerous) and mime_rep != sig_rep:
                mismatch = True
                detail = f"mime_spoof:{ctype}:{sig}"
            else:
                # Prefer signature (CONTENT_TYPE_HEADER_ONLY_TRUSTED=NO)
                detail = f"signature_overrides_mime:{ctype}:{sig}"
    elif mime_rep and (body or allow_mime_only_when_empty_body):
        chosen = mime_rep
    elif name_rep:
        chosen = name_rep
        detail = "filename_fallback"
    else:
        chosen = "UNKNOWN"

    if mismatch:
        raise AdapterFrameworkError("INVALID_CONTENT_TYPE", detail or "signature_mismatch")

    if chosen == "UNKNOWN" or chosen not in REPRESENTATION_CLASSES:
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", detail or "UNKNOWN")

    mode = REPRESENTATION_TO_MODE[chosen]
    return RepresentationDecision(
        representation=chosen,
        adapter_mode=mode,
        signature=sig,
        content_type_observed=ctype,
        mime_trusted=False,
        mismatch_fail_closed=False,
        detail=detail,
    )


def assert_representation_matches_adapter_mode(representation: str, mode: str) -> None:
    expected = REPRESENTATION_TO_MODE.get(representation)
    if expected != mode and not (representation == "PDF_IMAGE_ONLY" and mode == "PDF_TEXT"):
        raise AdapterFrameworkError("UNSUPPORTED_FORMAT", f"mode_mismatch:{representation}:{mode}")
