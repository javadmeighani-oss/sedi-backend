"""Invalidate derived I7 state when canonical I6/consent changes. No vectors."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i7.period_summaries import invalidate_summaries_for_user


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def invalidate_derived_memory_state(
    db: Session, user_id: int, *, reason: str, commit: bool = True
) -> dict[str, int]:
    summaries = invalidate_summaries_for_user(db, user_id, reason=reason, commit=False)
    now = _utcnow()
    profiles = (
        db.query(models.UserLifelongProfile)
        .filter(
            models.UserLifelongProfile.user_id == user_id,
            models.UserLifelongProfile.status == "active",
        )
        .all()
    )
    for row in profiles:
        row.status = "stale"
        row.superseded_at = now
    exports = (
        db.query(models.UserMemoryExportJob)
        .filter(
            models.UserMemoryExportJob.user_id == user_id,
            models.UserMemoryExportJob.status.in_(("queued", "running", "ready")),
        )
        .all()
    )
    for row in exports:
        row.status = "revoked"
        row.revoked_at = now
        row.error_code = f"INVALIDATED:{reason}"
    if commit:
        db.commit()
    else:
        db.flush()
    return {
        "summaries": summaries,
        "profiles": len(profiles),
        "export_jobs": len(exports),
    }
