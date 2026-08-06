"""I5-IMPL-W1-P02 — pure Knowledge Unit helpers (no DB).

Hash / dedupe / eligibility / PII-marker guards. Fail-closed on missing provenance.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Optional, Union

from backend.app.services.i5.enums import KnowledgeUnitRuntimeEligibility

_FIELD_SEP = "\x1f"

# Simple fail-closed markers — not a full PII classifier.
_PII_REFUSE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-like
    re.compile(r"(?i)\bssn\b"),
    re.compile(r"(?i)\bpassword\b"),
    re.compile(r"(?i)\bapi[_-]?key\b"),
    re.compile(r"(?i)\bsecret[_-]?key\b"),
)


class KnowledgeUnitServiceError(ValueError):
    """Fail-closed validation error for knowledge-unit helpers."""


def sha256_hex(payload: str) -> str:
    """Return lowercase SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _norm(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_deduplication_key(
    domain: str,
    topic: str,
    population: str,
    jurisdiction: str,
    normalized_content_canonical: str,
) -> str:
    """Deterministic dedupe key: SHA-256 of domain/topic/population/jurisdiction/content."""
    parts = (
        _norm(domain),
        _norm(topic),
        _norm(population),
        _norm(jurisdiction),
        _norm(normalized_content_canonical),
    )
    return sha256_hex(_FIELD_SEP.join(parts))


def build_canonical_hash(
    normalized_statement: str,
    domain: str,
    knowledge_type: str,
    *,
    language: str = "en",
    population: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    topic_taxonomy: Optional[str] = None,
    canonicalization_version: str = "v1",
) -> str:
    """Canonical content hash for a structured knowledge unit (SHA-256 hex)."""
    parts = (
        _norm(canonicalization_version),
        _norm(domain),
        _norm(knowledge_type),
        _norm(language),
        _norm(topic_taxonomy),
        _norm(population),
        _norm(jurisdiction),
        _norm(normalized_statement),
    )
    return sha256_hex(_FIELD_SEP.join(parts))


def _as_mapping(ku: Union[Mapping[str, Any], Any]) -> Mapping[str, Any]:
    if isinstance(ku, Mapping):
        return ku
    return {
        "provenance_complete": getattr(ku, "provenance_complete", None),
        "runtime_eligibility": getattr(ku, "runtime_eligibility", None),
    }


def evaluate_runtime_eligibility(
    ku: Union[Mapping[str, Any], Any],
) -> KnowledgeUnitRuntimeEligibility:
    """Fail-closed eligibility: without provenance_complete, always NOT_ELIGIBLE."""
    data = _as_mapping(ku)
    complete = bool(data.get("provenance_complete"))
    if not complete:
        return KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    raw = data.get("runtime_eligibility")
    if raw is None:
        return KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE
    try:
        return KnowledgeUnitRuntimeEligibility(str(raw))
    except ValueError:
        return KnowledgeUnitRuntimeEligibility.NOT_ELIGIBLE


def validate_no_pii_markers(text: str) -> None:
    """Refuse text that contains simple SSN/password/api_key markers (fail-closed)."""
    if text is None:
        raise KnowledgeUnitServiceError("PII_MARKER_REFUSED:null_text")
    sample = str(text)
    for pattern in _PII_REFUSE_PATTERNS:
        if pattern.search(sample):
            raise KnowledgeUnitServiceError("PII_MARKER_REFUSED")
