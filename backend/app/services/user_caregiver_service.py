"""Gate 1 caregiver contact registry."""

from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.gate1 import CaregiverCreateIn, CaregiverUpdateIn


class CaregiverNotFoundError(Exception):
    pass


def _row_to_dict(row: models.UserCaregiver) -> dict:
    return {
        "id": row.id,
        "owner_user_id": row.owner_user_id,
        "name": row.name,
        "phone": row.phone,
        "relationship": row.relationship,
        "priority": row.priority,
        "notify_daily_status": row.notify_daily_status,
        "notify_emergency": row.notify_emergency,
        "notify_care_summary": row.notify_care_summary,
        "can_manage_profile": row.can_manage_profile,
        "preferred_language": row.preferred_language,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_caregivers(db: Session, owner_user_id: int, *, active_only: bool = True) -> List[dict]:
    q = db.query(models.UserCaregiver).filter(models.UserCaregiver.owner_user_id == owner_user_id)
    if active_only:
        q = q.filter(models.UserCaregiver.is_active == True)  # noqa: E712
    rows = q.order_by(models.UserCaregiver.priority.asc(), models.UserCaregiver.id.asc()).all()
    return [_row_to_dict(r) for r in rows]


def create_caregiver(db: Session, owner_user_id: int, body: CaregiverCreateIn) -> dict:
    now = datetime.utcnow()
    row = models.UserCaregiver(
        owner_user_id=owner_user_id,
        name=body.name,
        phone=body.phone,
        relationship=body.relationship,
        priority=body.priority,
        notify_daily_status=body.notify_daily_status,
        notify_emergency=body.notify_emergency,
        notify_care_summary=body.notify_care_summary,
        can_manage_profile=body.can_manage_profile,
        preferred_language=body.preferred_language,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def update_caregiver(
    db: Session,
    owner_user_id: int,
    caregiver_id: int,
    body: CaregiverUpdateIn,
) -> dict:
    row = (
        db.query(models.UserCaregiver)
        .filter(
            models.UserCaregiver.id == caregiver_id,
            models.UserCaregiver.owner_user_id == owner_user_id,
        )
        .first()
    )
    if row is None:
        raise CaregiverNotFoundError()
    data = body.model_dump(exclude_unset=True)
    for key, val in data.items():
        setattr(row, key, val)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def deactivate_caregiver(db: Session, owner_user_id: int, caregiver_id: int) -> None:
    """Soft-delete: set is_active=false (safest; preserves audit trail)."""
    row = (
        db.query(models.UserCaregiver)
        .filter(
            models.UserCaregiver.id == caregiver_id,
            models.UserCaregiver.owner_user_id == owner_user_id,
        )
        .first()
    )
    if row is None:
        raise CaregiverNotFoundError()
    row.is_active = False
    row.updated_at = datetime.utcnow()
    db.commit()
