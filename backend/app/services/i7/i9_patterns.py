"""I9 -> I7 derived pattern provenance (no new architecture decision)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import PERM_WRITE, has_permission, _active_consent

GENERATOR = "i7-wave2-i9-patterns-v1"


def upsert_i9_derived_pattern(
    db: Session,
    *,
    user_id: int,
    pattern_key: str,
    pattern: dict[str, Any],
    source_refs: list[dict[str, Any]],
    commit: bool = True,
) -> Optional[models.UserI7DerivedPattern]:
    """Derive I7 pattern from I9 vitals only with explicit source provenance."""
    if not has_permission(db, user_id, PERM_WRITE):
        return None
    if not source_refs:
        raise ValueError("I9_SOURCE_REFS_REQUIRED")
    consent = _active_consent(db, user_id=user_id)
    prior = (
        db.query(models.UserI7DerivedPattern)
        .filter(
            models.UserI7DerivedPattern.user_id == user_id,
            models.UserI7DerivedPattern.pattern_key == pattern_key,
            models.UserI7DerivedPattern.status == "active",
        )
        .first()
    )
    if prior is not None:
        prior.status = "superseded"
        prior.superseded_at = datetime.now(timezone.utc)
    row = models.UserI7DerivedPattern(
        user_id=user_id,
        pattern_key=pattern_key,
        pattern_json=json.dumps(pattern, sort_keys=True),
        source_system="I9",
        source_refs_json=json.dumps(source_refs, sort_keys=True),
        provenance_json=json.dumps(
            {"generator": GENERATOR, "source_system": "I9", "pattern_key": pattern_key},
            sort_keys=True,
        ),
        consent_id=consent.id if consent else None,
        status="active",
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def list_active_i9_patterns(db: Session, user_id: int) -> list[models.UserI7DerivedPattern]:
    return (
        db.query(models.UserI7DerivedPattern)
        .filter(
            models.UserI7DerivedPattern.user_id == user_id,
            models.UserI7DerivedPattern.status == "active",
        )
        .order_by(models.UserI7DerivedPattern.created_at.desc())
        .all()
    )
