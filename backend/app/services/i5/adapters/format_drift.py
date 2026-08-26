"""Deterministic format / structure drift classification (no schema change)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SUPPORTED_AUTO_INGEST = frozenset(
    {
        "HTML",
        "JSON",
        "RSS_ATOM",
        "XML_JATS",
        "PDF_TEXT",
        "CSV_TSV",
        "DOCX",
    }
)

UNSUPPORTED_AUTO = frozenset({"PDF_IMAGE_ONLY", "UNKNOWN"})

DRIFT_CLASSES = frozenset(
    {
        "SAME_SUPPORTED_FORMAT",
        "FORMAT_CHANGED_SUPPORTED",
        "FORMAT_CHANGED_UNSUPPORTED",
        "STRUCTURE_DRIFT",
        "UNREACHABLE",
    }
)


@dataclass(frozen=True)
class FormatDriftDecision:
    classification: str
    previous_representation: Optional[str]
    current_representation: str
    same_source_identity: bool
    fail_closed: bool
    preserve_last_known_good: bool
    publish_new_evidence: bool
    rights_recheck_required: bool
    extraction_canary_required: bool
    detail: str = ""


def classify_format_drift(
    *,
    source_identity_key: str,
    previous_representation: Optional[str],
    current_representation: str,
    previous_structure_fingerprint: Optional[str] = None,
    current_structure_fingerprint: Optional[str] = None,
    unreachable: bool = False,
) -> FormatDriftDecision:
    """Classify representation change for a stable source identity."""
    if not (source_identity_key or "").strip():
        raise ValueError("SOURCE_IDENTITY_REQUIRED")

    if unreachable:
        return FormatDriftDecision(
            classification="UNREACHABLE",
            previous_representation=previous_representation,
            current_representation=current_representation or "UNKNOWN",
            same_source_identity=True,
            fail_closed=True,
            preserve_last_known_good=True,
            publish_new_evidence=False,
            rights_recheck_required=False,
            extraction_canary_required=False,
            detail="unreachable",
        )

    prev = (previous_representation or "").upper() or None
    cur = (current_representation or "").upper()

    if cur in UNSUPPORTED_AUTO or cur not in SUPPORTED_AUTO_INGEST | UNSUPPORTED_AUTO:
        return FormatDriftDecision(
            classification="FORMAT_CHANGED_UNSUPPORTED",
            previous_representation=prev,
            current_representation=cur,
            same_source_identity=True,
            fail_closed=True,
            preserve_last_known_good=True,
            publish_new_evidence=False,
            rights_recheck_required=True,
            extraction_canary_required=False,
            detail="unsupported_or_unknown",
        )

    if prev is None or prev == cur:
        # Same format — optional structure drift
        if (
            prev is not None
            and previous_structure_fingerprint
            and current_structure_fingerprint
            and previous_structure_fingerprint != current_structure_fingerprint
        ):
            return FormatDriftDecision(
                classification="STRUCTURE_DRIFT",
                previous_representation=prev,
                current_representation=cur,
                same_source_identity=True,
                fail_closed=False,
                preserve_last_known_good=True,
                publish_new_evidence=True,
                rights_recheck_required=False,
                extraction_canary_required=True,
                detail="structure_fingerprint_changed",
            )
        return FormatDriftDecision(
            classification="SAME_SUPPORTED_FORMAT",
            previous_representation=prev,
            current_representation=cur,
            same_source_identity=True,
            fail_closed=False,
            preserve_last_known_good=True,
            publish_new_evidence=True,
            rights_recheck_required=False,
            extraction_canary_required=False,
            detail="unchanged_or_first_observe",
        )

    # Format changed
    if cur in SUPPORTED_AUTO_INGEST:
        return FormatDriftDecision(
            classification="FORMAT_CHANGED_SUPPORTED",
            previous_representation=prev,
            current_representation=cur,
            same_source_identity=True,
            fail_closed=False,
            preserve_last_known_good=True,
            publish_new_evidence=True,
            rights_recheck_required=True,
            extraction_canary_required=True,
            detail=f"{prev}->{cur}",
        )

    return FormatDriftDecision(
        classification="FORMAT_CHANGED_UNSUPPORTED",
        previous_representation=prev,
        current_representation=cur,
        same_source_identity=True,
        fail_closed=True,
        preserve_last_known_good=True,
        publish_new_evidence=False,
        rights_recheck_required=True,
        extraction_canary_required=False,
        detail=f"{prev}->{cur}",
    )


def structure_fingerprint_for_representation(representation: str, body: bytes) -> str:
    """Bounded structure fingerprint (not a content hash) for drift detection."""
    import hashlib
    import re

    rep = (representation or "").upper()
    sample = (body or b"")[:65536]
    if rep == "HTML":
        tags = re.findall(rb"<(?:div|section|article|main|h[1-6]|p)\b", sample.lower())
        return hashlib.sha256(b"html:" + b",".join(sorted(set(tags))[:40])).hexdigest()[:32]
    if rep == "JSON":
        keys = re.findall(rb'"([A-Za-z0-9_]{1,40})"\s*:', sample)
        return hashlib.sha256(b"json:" + b",".join(sorted(set(keys))[:80])).hexdigest()[:32]
    if rep in {"RSS_ATOM", "XML_JATS"}:
        tags = re.findall(rb"<([A-Za-z0-9:_-]{1,40})", sample)
        return hashlib.sha256(b"xml:" + b",".join(sorted(set(tags))[:80])).hexdigest()[:32]
    if rep == "CSV_TSV":
        first = sample.splitlines()[0] if sample.splitlines() else b""
        return hashlib.sha256(b"tab:" + first[:512]).hexdigest()[:32]
    return hashlib.sha256(b"raw:" + sample[:2048]).hexdigest()[:32]
