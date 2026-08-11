"""Canonical acquisition / evidence boundary for governed fetches.

GOVERNED_FETCH_COMPLETED != KNOWLEDGE_PUBLISHED.
Creates metadata-only I5RawEvidence (storage_mode=NONE) when rights ALLOWED.
Never fabricates KnowledgeUnit / clinical recommendation.
Never persists raw body bytes (table has no body column; byte_size stays None).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i5.enums import (
    RawRetentionMode,
    RawStorageMode,
    RightsTermsState,
    RobotsAccessState,
)


def _normalize_content_hash(content_hash: Optional[str], *, fallback_seed: str) -> str:
    h = (content_hash or "").strip().lower()
    if len(h) == 64 and all(c in "0123456789abcdef" for c in h):
        return h
    return hashlib.sha256(fallback_seed.encode("utf-8")).hexdigest()


def record_acquisition_evidence_boundary(
    db: Session,
    *,
    source_profile_id: int,
    canonical_url: str,
    content_hash: Optional[str],
    rights_decision: str,
    connector_key: str = "",
    weekly_run_id: Optional[int] = None,
    mime_type: str = "application/json",
) -> Optional[int]:
    """Persist hash/link acquisition lineage when RIGHTS_ALLOWED.

    Returns raw_evidence.id or None when blocked (DENIED/UNKNOWN) or invalid input.
    """
    rights = (rights_decision or "").strip().upper()
    if rights != "RIGHTS_ALLOWED":
        return None
    url = (canonical_url or "").strip()
    if not url:
        return None

    digest = _normalize_content_hash(
        content_hash, fallback_seed=f"{connector_key}|{source_profile_id}|{url}"
    )
    existing = (
        db.query(models.I5RawEvidence)
        .filter_by(
            content_hash=digest,
            source_profile_id=source_profile_id,
            canonical_url=url,
        )
        .first()
    )
    if existing is not None:
        return int(existing.id)

    raw = models.I5RawEvidence(
        source_profile_id=source_profile_id,
        source_document_id=(connector_key or None),
        source_version_id="acquisition_v1",
        retrieval_run_id=weekly_run_id,
        retrieval_timestamp=datetime.utcnow(),
        canonical_url=url,
        content_hash=digest,
        byte_hash=digest,
        hash_algorithm="SHA-256",
        mime_type=mime_type,
        language="en",
        storage_mode=RawStorageMode.NONE.value,
        retention_mode=RawRetentionMode.RAW_LINK_AND_CITATION_ONLY.value,
        rights_terms_state=RightsTermsState.APPROVED.value,
        robots_access_state=RobotsAccessState.ALLOWED.value,
        redaction_state="NONE",
        prohibited_data_state="UNKNOWN",
        expiry_state="ACTIVE",
        created_by_run_id=weekly_run_id,
        byte_size=None,
        storage_locator=None,
        object_key=None,
        durable_path=None,
        recoverability_state="ABSENCE_GOVERNED",
    )
    db.add(raw)
    db.flush()
    return int(raw.id)


def count_persisted_raw_with_body_residue(db: Session, *, source_profile_id: int) -> int:
    """Count raw rows that claim body retention (should be 0 under NO_STORE/DENIED)."""
    return (
        db.query(models.I5RawEvidence)
        .filter(
            models.I5RawEvidence.source_profile_id == source_profile_id,
            models.I5RawEvidence.byte_size.isnot(None),
            models.I5RawEvidence.byte_size > 0,
        )
        .count()
    )
