"""Durable unsupported-format capability gap persistence.

FORMAT_GAP_PERSISTENCE_AUTHORITY=knowledge_gaps (KnowledgeGap)
Semantic justification:
  - gap_type=RUNTIME_RETRIEVAL_FAILURE covers fail-closed retrieval/format inability
  - blocker carries UNSUPPORTED_FORMAT:<format> for durable review
  - target_source_profile_id preserves source identity
  - canonical_gap_key enables dedupe / versioning via retry_count
  - no new table/enum/CHECK/migration required

Optional corroboration: i5_source_coverage_gaps.detail may mirror the same code.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    KnowledgeGapPriority,
    KnowledgeGapSeverity,
    KnowledgeGapStatus,
    KnowledgeGapType,
    KnowledgeGapUrgency,
    SourceCoverageStatus,
)


FORMAT_GAP_PERSISTENCE_AUTHORITY = "knowledge_gaps:KnowledgeGap"
UNSUPPORTED_FORMAT_PREFIX = "UNSUPPORTED_FORMAT"


def _canonical_format_gap_key(
    *,
    source_profile_id: int,
    resource_ref: str,
    format_id: str,
) -> str:
    raw = f"unsupported_format|v1|{source_profile_id}|{resource_ref}|{format_id.upper()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def persist_unsupported_format_gap(
    db: Session,
    *,
    source_profile_id: int,
    resource_ref: str,
    format_id: str,
    domain: str = "format_capability",
    subdomain: Optional[str] = None,
    discovered_by: str = "format_capability_matrix",
    also_coverage_gap: bool = True,
) -> Tuple[models.KnowledgeGap, bool]:
    """Persist or version an unsupported-format gap. Returns (row, created_new)."""
    fmt = (format_id or "UNKNOWN").upper()
    ref = (resource_ref or "").strip() or "unspecified_resource"
    key = _canonical_format_gap_key(
        source_profile_id=source_profile_id, resource_ref=ref, format_id=fmt
    )
    existing = db.query(models.KnowledgeGap).filter_by(canonical_gap_key=key).first()
    blocker = f"{UNSUPPORTED_FORMAT_PREFIX}:{fmt}"
    title = f"Unsupported format {fmt} for source {source_profile_id}"
    if existing is not None:
        existing.retry_count = int(existing.retry_count or 0) + 1
        existing.last_attempt_at = datetime.utcnow()
        existing.blocker = blocker[:2000]
        existing.status = KnowledgeGapStatus.OPEN.value
        existing.updated_at = datetime.utcnow()
        existing.row_version = int(existing.row_version or 1) + 1
        db.flush()
        return existing, False

    gap = models.KnowledgeGap(
        canonical_gap_key=key,
        domain=domain[:128],
        subdomain=(subdomain or fmt)[:128] if subdomain or fmt else None,
        gap_type=KnowledgeGapType.RUNTIME_RETRIEVAL_FAILURE.value,
        title=title[:512],
        description=(
            f"Adapter routing failed closed on unsupported format {fmt} "
            f"for resource {ref}. Ingestion must not continue."
        )[:8000],
        evidence_of_gap=f"resource_ref={ref};format={fmt};source_profile_id={source_profile_id}",
        current_knowledge_state="FORMAT_UNSUPPORTED",
        required_knowledge_state="FORMAT_SUPPORTED_OR_GOVERNED_DEFER",
        source_need=f"format_adapter:{fmt}",
        priority=KnowledgeGapPriority.P1.value,
        severity=KnowledgeGapSeverity.HIGH.value,
        urgency=KnowledgeGapUrgency.NORMAL.value,
        status=KnowledgeGapStatus.OPEN.value,
        blocker=blocker[:2000],
        target_source_profile_id=source_profile_id,
        discovered_by=discovered_by[:512],
        next_action="GOVERNANCE_REVIEW_FORMAT_CAPABILITY_OR_DEFER",
        last_attempt_at=datetime.utcnow(),
        retry_count=0,
    )
    db.add(gap)
    db.flush()

    if also_coverage_gap:
        mirror = models.I5SourceCoverageGap(
            disease_or_domain=domain[:128],
            knowledge_dimension="FORMAT_CAPABILITY",
            evidence_class=fmt,
            status=SourceCoverageStatus.SOURCE_DISCOVERY_REQUIRED.value,
            detail=f"{blocker};resource_ref={ref};knowledge_gap_id={{pending}}",
            knowledge_gap_id=gap.id,
        )
        db.add(mirror)
        db.flush()
        mirror.detail = f"{blocker};resource_ref={ref};knowledge_gap_id={gap.id}"
        db.flush()

    return gap, True


def record_unsupported_format_from_error(
    db: Session,
    *,
    source_profile_id: int,
    resource_ref: str,
    error: BaseException,
) -> Tuple[models.KnowledgeGap, bool]:
    """Map AdapterFrameworkError('UNSUPPORTED_FORMAT', ...) → durable gap."""
    fmt = "UNKNOWN"
    args = getattr(error, "args", ()) or ()
    if len(args) >= 2 and str(args[0]).upper() == UNSUPPORTED_FORMAT_PREFIX:
        fmt = str(args[1])
    elif len(args) >= 1 and UNSUPPORTED_FORMAT_PREFIX in str(args[0]).upper():
        # message form
        parts = str(args[0]).split(":", 1)
        fmt = parts[1].strip() if len(parts) > 1 else "UNKNOWN"
    return persist_unsupported_format_gap(
        db,
        source_profile_id=source_profile_id,
        resource_ref=resource_ref,
        format_id=fmt,
    )


def requery_unsupported_format_gap(
    db: Session,
    *,
    source_profile_id: int,
    resource_ref: str,
    format_id: str,
) -> Optional[models.KnowledgeGap]:
    key = _canonical_format_gap_key(
        source_profile_id=source_profile_id,
        resource_ref=resource_ref,
        format_id=format_id,
    )
    return db.query(models.KnowledgeGap).filter_by(canonical_gap_key=key).first()


def format_gap_persistence_authority() -> dict[str, Any]:
    return {
        "FORMAT_GAP_PERSISTENCE_AUTHORITY": FORMAT_GAP_PERSISTENCE_AUTHORITY,
        "gap_type": KnowledgeGapType.RUNTIME_RETRIEVAL_FAILURE.value,
        "blocker_prefix": UNSUPPORTED_FORMAT_PREFIX,
        "optional_mirror": "i5_source_coverage_gaps",
        "justification": (
            "RUNTIME_RETRIEVAL_FAILURE + UNSUPPORTED_FORMAT blocker truthfully represents "
            "a fail-closed format capability gap without inventing a new vocabulary."
        ),
    }
