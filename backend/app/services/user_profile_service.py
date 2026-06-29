"""Unified user identity/profile read and update (Phase V1.1A + Gate 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.auth_otp import MeOut, MeUpdateIn
from backend.app.services.knowledge.service import ensure_profile_core


def build_me_response(db: Session, user: models.User) -> dict:
    """Build GET/PATCH /auth/me payload from User + UserProfileCore."""
    profile = (
        db.query(models.UserProfileCore)
        .filter(models.UserProfileCore.user_id == user.id)
        .first()
    )
    name = user.name
    preferred_language = user.preferred_language or "en"
    account_type = getattr(user, "account_type", None) or "normal"
    return MeOut(
        user_id=user.id,
        phone=user.phone,
        name=name,
        preferred_language=preferred_language,
        account_type=account_type,
        birth_year=profile.birth_year if profile else None,
        date_of_birth=profile.date_of_birth if profile else None,
        sex=profile.sex if profile else None,
        addressing_preference=profile.addressing_preference if profile else None,
        timezone=profile.timezone if profile else None,
        height_cm=profile.height_cm if profile else None,
        weight_kg=profile.weight_kg if profile else None,
        display_name=name,
        language=preferred_language,
    ).model_dump()


def apply_profile_update(db: Session, user: models.User, body: MeUpdateIn) -> models.User:
    """Apply PATCH fields to User and UserProfileCore (lazy-create core row)."""
    profile: Optional[models.UserProfileCore] = None
    core_fields_set = any(
        v is not None
        for v in (
            body.birth_year,
            body.date_of_birth,
            body.sex,
            body.addressing_preference,
            body.timezone,
            body.height_cm,
            body.weight_kg,
        )
    )

    name_value = body.resolved_name()
    if name_value is not None:
        user.name = name_value
        knowledge = (
            db.query(models.UserProfileKnowledge)
            .filter(models.UserProfileKnowledge.user_id == user.id)
            .first()
        )
        if knowledge is not None:
            knowledge.display_name = name_value
            knowledge.updated_at = datetime.utcnow()

    if body.preferred_language is not None:
        user.preferred_language = body.preferred_language

    if core_fields_set:
        profile = ensure_profile_core(db, user.id)
        if body.birth_year is not None:
            profile.birth_year = body.birth_year
        if body.date_of_birth is not None:
            profile.date_of_birth = body.date_of_birth
            profile.birth_year = body.date_of_birth.year
        if body.sex is not None:
            profile.sex = body.sex.strip() if body.sex.strip() else None
        if body.addressing_preference is not None:
            ap = body.addressing_preference.strip()
            profile.addressing_preference = ap if ap else None
        if body.timezone is not None:
            profile.timezone = body.timezone.strip() if body.timezone.strip() else None
        if body.height_cm is not None:
            profile.height_cm = body.height_cm
        if body.weight_kg is not None:
            profile.weight_kg = body.weight_kg
        profile.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(user)
    return user
