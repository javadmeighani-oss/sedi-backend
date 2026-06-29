"""Gate 1 dependent (special) user management."""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.gate1 import DependentCreateIn, DependentUpdateIn
from backend.app.services.gate1_access import DEFAULT_DEPENDENT_PERMISSIONS
from backend.app.services.knowledge.service import ensure_profile_core
from backend.app.services.gate1_access import validate_iana_timezone


class DependentNotFoundError(Exception):
    pass


class DependentAccessDeniedError(Exception):
    pass


def _relationship_row(
    db: Session,
    caregiver_user_id: int,
    dependent_user_id: int,
) -> Optional[models.UserCareRelationship]:
    return (
        db.query(models.UserCareRelationship)
        .filter(
            models.UserCareRelationship.caregiver_user_id == caregiver_user_id,
            models.UserCareRelationship.dependent_user_id == dependent_user_id,
        )
        .first()
    )


def _dependent_out(
    db: Session,
    caregiver_user_id: int,
    dependent: models.User,
    rel: models.UserCareRelationship,
) -> dict:
    profile = (
        db.query(models.UserProfileCore)
        .filter(models.UserProfileCore.user_id == dependent.id)
        .first()
    )
    return {
        "dependent_user_id": dependent.id,
        "account_type": dependent.account_type or "dependent",
        "name": dependent.name,
        "preferred_language": dependent.preferred_language,
        "birth_year": profile.birth_year if profile else None,
        "date_of_birth": profile.date_of_birth if profile else None,
        "sex": profile.sex if profile else None,
        "addressing_preference": profile.addressing_preference if profile else None,
        "timezone": profile.timezone if profile else None,
        "relationship": rel.relationship,
        "priority": rel.priority,
        "is_active": rel.is_active,
        "created_at": rel.created_at,
        "updated_at": rel.updated_at,
    }


def list_dependents(db: Session, caregiver_user_id: int, *, active_only: bool = True) -> List[dict]:
    q = db.query(models.UserCareRelationship).filter(
        models.UserCareRelationship.caregiver_user_id == caregiver_user_id,
    )
    if active_only:
        q = q.filter(models.UserCareRelationship.is_active == True)  # noqa: E712
    rels = q.order_by(models.UserCareRelationship.priority.asc()).all()
    out: List[dict] = []
    for rel in rels:
        dep = db.query(models.User).filter(models.User.id == rel.dependent_user_id).first()
        if dep is None:
            continue
        out.append(_dependent_out(db, caregiver_user_id, dep, rel))
    return out


def get_dependent(db: Session, caregiver_user_id: int, dependent_user_id: int) -> dict:
    rel = _relationship_row(db, caregiver_user_id, dependent_user_id)
    if rel is None or not rel.is_active:
        raise DependentNotFoundError()
    dep = db.query(models.User).filter(models.User.id == dependent_user_id).first()
    if dep is None:
        raise DependentNotFoundError()
    return _dependent_out(db, caregiver_user_id, dep, rel)


def create_dependent(db: Session, caregiver_user_id: int, body: DependentCreateIn) -> dict:
    caregiver = db.query(models.User).filter(models.User.id == caregiver_user_id).first()
    if caregiver is None:
        raise DependentAccessDeniedError()
    if getattr(caregiver, "account_type", "normal") == "dependent":
        raise DependentAccessDeniedError("Dependent users cannot create other dependents")

    if body.timezone:
        validate_iana_timezone(body.timezone)

    now = datetime.utcnow()
    dependent = models.User(
        name=body.name.strip(),
        secret_key="dependent-placeholder",
        preferred_language=body.preferred_language,
        account_type="dependent",
        phone=None,
        created_at=now,
    )
    db.add(dependent)
    db.flush()

    profile = ensure_profile_core(db, dependent.id)
    if body.birth_year is not None:
        profile.birth_year = body.birth_year
    if body.date_of_birth is not None:
        profile.date_of_birth = body.date_of_birth
        profile.birth_year = body.date_of_birth.year
    if body.sex is not None:
        profile.sex = body.sex.strip() or None
    if body.addressing_preference is not None:
        ap = body.addressing_preference.strip()
        profile.addressing_preference = ap if ap else None
    if body.timezone is not None:
        profile.timezone = validate_iana_timezone(body.timezone)
    profile.updated_at = now

    rel = models.UserCareRelationship(
        caregiver_user_id=caregiver_user_id,
        dependent_user_id=dependent.id,
        relationship=body.relationship,
        permissions_json=json.dumps(DEFAULT_DEPENDENT_PERMISSIONS),
        priority=body.priority,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(rel)
    db.commit()
    db.refresh(dependent)
    db.refresh(rel)
    return _dependent_out(db, caregiver_user_id, dependent, rel)


def update_dependent(
    db: Session,
    caregiver_user_id: int,
    dependent_user_id: int,
    body: DependentUpdateIn,
) -> dict:
    rel = _relationship_row(db, caregiver_user_id, dependent_user_id)
    if rel is None:
        raise DependentNotFoundError()
    dep = db.query(models.User).filter(models.User.id == dependent_user_id).first()
    if dep is None or dep.account_type != "dependent":
        raise DependentNotFoundError()

    if body.name is not None:
        dep.name = body.name.strip()
    if body.preferred_language is not None:
        dep.preferred_language = body.preferred_language

    profile = ensure_profile_core(db, dependent_user_id)
    if body.birth_year is not None:
        profile.birth_year = body.birth_year
    if body.date_of_birth is not None:
        profile.date_of_birth = body.date_of_birth
        profile.birth_year = body.date_of_birth.year
    if body.sex is not None:
        profile.sex = body.sex.strip() or None
    if body.addressing_preference is not None:
        ap = (body.addressing_preference or "").strip()
        profile.addressing_preference = ap if ap else None
    if body.timezone is not None:
        profile.timezone = validate_iana_timezone(body.timezone)
    profile.updated_at = datetime.utcnow()

    if body.relationship is not None:
        rel.relationship = body.relationship
    if body.priority is not None:
        rel.priority = body.priority
    if body.is_active is not None:
        rel.is_active = body.is_active
    rel.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(dep)
    db.refresh(rel)
    return _dependent_out(db, caregiver_user_id, dep, rel)


def deactivate_dependent(db: Session, caregiver_user_id: int, dependent_user_id: int) -> None:
    rel = _relationship_row(db, caregiver_user_id, dependent_user_id)
    if rel is None:
        raise DependentNotFoundError()
    rel.is_active = False
    rel.updated_at = datetime.utcnow()
    db.commit()
