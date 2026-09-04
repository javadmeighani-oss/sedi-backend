"""C04 HealthSubject-bound clinical condition authority (not Account-owned)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    account_can_access_subject,
    require_account_subject_access,
)

SOURCE_SELF_REPORTED = "SELF_REPORTED"
SOURCE_CAREGIVER_REPORTED = "CAREGIVER_REPORTED"
SOURCE_CLINICAL = "CLINICAL"
SOURCE_IMPORTED = "IMPORTED"
SOURCE_SYSTEM_SUGGESTED = "SYSTEM_SUGGESTED"

ALLOWED_SOURCES = frozenset(
    {
        SOURCE_SELF_REPORTED,
        SOURCE_CAREGIVER_REPORTED,
        SOURCE_CLINICAL,
        SOURCE_IMPORTED,
        SOURCE_SYSTEM_SUGGESTED,
    }
)

VERIFICATION_REPORTED_UNVERIFIED = "REPORTED_UNVERIFIED"
VERIFICATION_VERIFIED = "VERIFIED"
VERIFICATION_DISPUTED = "DISPUTED"
VERIFICATION_UNKNOWN = "UNKNOWN"

ALLOWED_VERIFICATIONS = frozenset(
    {
        VERIFICATION_REPORTED_UNVERIFIED,
        VERIFICATION_VERIFIED,
        VERIFICATION_DISPUTED,
        VERIFICATION_UNKNOWN,
    }
)

# Caregiver/self report paths may not auto-elevate to clinician verified.
REPORT_PATH_SOURCES = frozenset({SOURCE_SELF_REPORTED, SOURCE_CAREGIVER_REPORTED})


class HealthSubjectConditionError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _active_access_role(db: Session, account_user_id: int, health_subject_id: int) -> Optional[str]:
    row = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == account_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .order_by(models.AccountHealthSubjectAccess.id.asc())
        .first()
    )
    return row.access_role if row else None


def infer_report_source_class(*, access_role: str) -> str:
    if access_role == "SELF":
        return SOURCE_SELF_REPORTED
    if access_role in ("CAREGIVER", "MANAGER"):
        return SOURCE_CAREGIVER_REPORTED
    raise HealthSubjectConditionError("INVALID_ACCESS_ROLE")


def list_active_subject_conditions(
    db: Session,
    *,
    actor_account_user_id: int,
    health_subject_id: int,
) -> list[models.HealthSubjectCondition]:
    require_account_subject_access(db, actor_account_user_id, health_subject_id)
    return (
        db.query(models.HealthSubjectCondition)
        .filter(
            models.HealthSubjectCondition.health_subject_id == health_subject_id,
            models.HealthSubjectCondition.status == "active",
        )
        .order_by(models.HealthSubjectCondition.id.asc())
        .all()
    )


def report_subject_condition(
    db: Session,
    *,
    actor_account_user_id: int,
    health_subject_id: int,
    condition_id: int,
    source_class: Optional[str] = None,
    verification_state: Optional[str] = None,
    severity: Optional[str] = None,
    notes: Optional[str] = None,
    diagnosed_date: Optional[datetime] = None,
    commit: bool = True,
) -> models.HealthSubjectCondition:
    """Governed report of a catalog condition onto a HealthSubject.

    Caregiver/self report paths always land as REPORTED_UNVERIFIED unless an
    explicitly authorized clinical/import source is used. I5/RAG/LLM/I7/I8/I9/I10
    have no call path into this function.
    """
    subject = require_account_subject_access(db, actor_account_user_id, health_subject_id)
    if subject.status != "active":
        raise HealthSubjectConditionError("HEALTH_SUBJECT_INACTIVE")

    role = _active_access_role(db, actor_account_user_id, health_subject_id)
    if role is None:
        raise HealthSubjectAccessDenied()

    condition = db.query(models.MedicalCondition).filter(models.MedicalCondition.id == condition_id).first()
    if condition is None:
        raise HealthSubjectConditionError("CONDITION_NOT_FOUND")

    resolved_source = source_class or infer_report_source_class(access_role=role)
    if resolved_source not in ALLOWED_SOURCES:
        raise HealthSubjectConditionError("INVALID_SOURCE_CLASS")

    # Actor may not claim CLINICAL/IMPORTED verification elevation via this gate.
    if resolved_source in REPORT_PATH_SOURCES:
        if source_class in (SOURCE_CLINICAL, SOURCE_IMPORTED, SOURCE_SYSTEM_SUGGESTED):
            raise HealthSubjectConditionError("SOURCE_NOT_ALLOWED_FOR_ACTOR")
        resolved_verification = VERIFICATION_REPORTED_UNVERIFIED
    else:
        # CLINICAL / IMPORTED / SYSTEM_SUGGESTED reserved — not opened for caregiver API in C04.
        raise HealthSubjectConditionError("SOURCE_NOT_ALLOWED_FOR_ACTOR")

    if verification_state is not None:
        if verification_state not in ALLOWED_VERIFICATIONS:
            raise HealthSubjectConditionError("INVALID_VERIFICATION_STATE")
        # Never allow caregiver/self report to set VERIFIED in C04.
        if resolved_source in REPORT_PATH_SOURCES and verification_state == VERIFICATION_VERIFIED:
            raise HealthSubjectConditionError("VERIFICATION_ELEVATION_FORBIDDEN")
        if resolved_source in REPORT_PATH_SOURCES:
            resolved_verification = (
                verification_state
                if verification_state in (VERIFICATION_REPORTED_UNVERIFIED, VERIFICATION_DISPUTED, VERIFICATION_UNKNOWN)
                else VERIFICATION_REPORTED_UNVERIFIED
            )

    existing = (
        db.query(models.HealthSubjectCondition)
        .filter(
            models.HealthSubjectCondition.health_subject_id == health_subject_id,
            models.HealthSubjectCondition.condition_id == condition_id,
            models.HealthSubjectCondition.status == "active",
        )
        .first()
    )
    now = _utc_now()
    if existing is not None:
        if severity is not None:
            existing.severity = severity
        if notes is not None:
            existing.notes = notes
        if diagnosed_date is not None:
            existing.diagnosed_date = diagnosed_date
        existing.reported_by_account_user_id = actor_account_user_id
        existing.source_class = resolved_source
        existing.verification_state = resolved_verification
        existing.updated_at = now
        if commit:
            db.commit()
            db.refresh(existing)
        else:
            db.flush()
        return existing

    row = models.HealthSubjectCondition(
        health_subject_id=health_subject_id,
        condition_id=condition_id,
        reported_by_account_user_id=actor_account_user_id,
        source_class=resolved_source,
        verification_state=resolved_verification,
        status="active",
        severity=severity,
        notes=notes,
        diagnosed_date=diagnosed_date,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def retract_subject_condition(
    db: Session,
    *,
    actor_account_user_id: int,
    health_subject_id: int,
    condition_id: int,
    commit: bool = True,
) -> bool:
    require_account_subject_access(db, actor_account_user_id, health_subject_id)
    row = (
        db.query(models.HealthSubjectCondition)
        .filter(
            models.HealthSubjectCondition.health_subject_id == health_subject_id,
            models.HealthSubjectCondition.condition_id == condition_id,
            models.HealthSubjectCondition.status == "active",
        )
        .first()
    )
    if row is None:
        return False
    row.status = "retracted"
    row.updated_at = _utc_now()
    if commit:
        db.commit()
    else:
        db.flush()
    return True


def condition_payload(db: Session, row: models.HealthSubjectCondition) -> dict:
    cond = db.query(models.MedicalCondition).filter(models.MedicalCondition.id == row.condition_id).first()
    return {
        "id": row.id,
        "health_subject_id": row.health_subject_id,
        "condition_id": row.condition_id,
        "condition_name": cond.name if cond else None,
        "condition_code": cond.code if cond else None,
        "reported_by_account_user_id": row.reported_by_account_user_id,
        "source_class": row.source_class,
        "verification_state": row.verification_state,
        "status": row.status,
        "severity": row.severity,
        "notes": row.notes,
        "diagnosed_date": row.diagnosed_date.isoformat() if row.diagnosed_date else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def account_can_access_subject_safe(db: Session, account_user_id: int, health_subject_id: int) -> bool:
    return account_can_access_subject(db, account_user_id, health_subject_id)
