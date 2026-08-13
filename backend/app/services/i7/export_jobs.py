"""Export job control-plane. No object-store provider. Not SoT."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i6.consent_service import PERM_READ, require_permission
from backend.app.services.i6.memory_writes import export_memory_bundle

SCHEMA_VERSION = "memory-bundle-v1"
GENERATOR_VERSION = "i7-v1-export-job"
CONTENT_CLASS = "MEMORY_BUNDLE"
EXPIRE_DAYS = 7


class ExportJobError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_export_job(
    db: Session, user_id: int, *, actor_user_id: Optional[int] = None, commit: bool = True
) -> models.UserMemoryExportJob:
    if actor_user_id is not None and int(actor_user_id) != int(user_id):
        raise ExportJobError("CROSS_USER_EXPORT_FORBIDDEN")
    require_permission(db, user_id, PERM_READ)
    consent = (
        db.query(models.UserConsent)
        .filter(
            models.UserConsent.subject_user_id == user_id,
            models.UserConsent.status == "active",
        )
        .first()
    )
    now = _utcnow()
    row = models.UserMemoryExportJob(
        user_id=user_id,
        status="queued",
        schema_version=SCHEMA_VERSION,
        generator_version=GENERATOR_VERSION,
        content_class=CONTENT_CLASS,
        created_at=now,
        expires_at=now + timedelta(days=EXPIRE_DAYS),
        consent_id=consent.id if consent is not None else None,
        actor_user_id=actor_user_id or user_id,
    )
    db.add(row)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(row)
    return row


def materialize_export_job(
    db: Session, job_id: int, user_id: int, *, commit: bool = True
) -> models.UserMemoryExportJob:
    """Build in-process bundle and record a control-plane receipt. No blob store."""
    require_permission(db, user_id, PERM_READ)
    row = (
        db.query(models.UserMemoryExportJob)
        .filter(
            models.UserMemoryExportJob.id == job_id,
            models.UserMemoryExportJob.user_id == user_id,
        )
        .first()
    )
    if row is None:
        raise ExportJobError("EXPORT_JOB_NOT_FOUND")
    if row.status in {"expired", "revoked"}:
        raise ExportJobError("EXPORT_JOB_NOT_ACTIVE")
    bundle = export_memory_bundle(db, user_id)
    payload = json.dumps(bundle, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    row.status = "ready"
    row.artifact_sha256 = digest
    row.artifact_bytes = len(payload.encode("utf-8"))
    row.artifact_uri = f"memory://user/{user_id}/export/{row.id}"
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(row)
    return row


def expire_due_export_jobs(db: Session, *, commit: bool = True) -> int:
    now = _utcnow()
    rows = (
        db.query(models.UserMemoryExportJob)
        .filter(
            models.UserMemoryExportJob.status.in_(("queued", "running", "ready")),
            models.UserMemoryExportJob.expires_at.isnot(None),
            models.UserMemoryExportJob.expires_at <= now,
        )
        .all()
    )
    for row in rows:
        row.status = "expired"
    if rows and commit:
        db.commit()
    elif rows:
        db.flush()
    return len(rows)
