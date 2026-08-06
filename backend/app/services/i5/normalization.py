"""I5-IMPL-W3-P01 — content normalization + dedupe key (no knowledge approval)."""
from __future__ import annotations

import hashlib
import re
import unicodedata

from backend.app.schemas.i5_adapters import NormalizedDocument
from backend.app.services.i5.adapters.base import AdapterFrameworkError, sha256_hex

_WS = re.compile(r"\s+")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def canonicalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = _CTRL.sub(" ", value)
    value = _WS.sub(" ", value).strip().casefold()
    return value


def build_dedupe_key(
    *,
    domain: str,
    topic: str,
    population: str,
    jurisdiction: str,
    normalized_content_canonical: str,
) -> str:
    """Frozen: hash(domain, topic, population, jurisdiction, normalized_content_canonical)."""
    payload = "\x1f".join(
        [
            canonicalize_text(domain),
            canonicalize_text(topic),
            canonicalize_text(population),
            canonicalize_text(jurisdiction),
            canonicalize_text(normalized_content_canonical),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_document(
    *,
    raw_text: str,
    domain: str,
    topic: str,
    population: str = "general",
    jurisdiction: str = "ZZ",
    language: str = "en",
) -> NormalizedDocument:
    if not (raw_text or "").strip():
        raise AdapterFrameworkError("PARSING_FAILED", "empty")
    canonical = canonicalize_text(raw_text)
    if not canonical:
        raise AdapterFrameworkError("PARSING_FAILED", "empty_canonical")
    content_hash = sha256_hex(canonical.encode("utf-8"))
    dedupe = build_dedupe_key(
        domain=domain,
        topic=topic,
        population=population,
        jurisdiction=jurisdiction,
        normalized_content_canonical=canonical,
    )
    return NormalizedDocument(
        domain=canonicalize_text(domain),
        topic=canonicalize_text(topic),
        population=canonicalize_text(population),
        jurisdiction=canonicalize_text(jurisdiction),
        normalized_content_canonical=canonical,
        content_hash=content_hash,
        dedupe_key=dedupe,
        language=language,
    )


def detect_no_material_change(previous_hash: str, current_hash: str) -> bool:
    left = (previous_hash or "").strip().lower()
    right = (current_hash or "").strip().lower()
    if len(left) != 64 or len(right) != 64:
        raise AdapterFrameworkError("PROVENANCE_INCOMPLETE", "hash")
    return left == right
