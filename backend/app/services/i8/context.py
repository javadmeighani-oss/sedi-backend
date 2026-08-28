"""Read-only trusted user context for I8 decision graph."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.i8_projection_service import (
    I8GovernedPhysiologicalContext,
    get_i8_governed_context_projection,
    projection_context_refs,
)


@dataclass
class I8TrustedContext:
    user_id: int
    allergies: list[str] = field(default_factory=list)
    unverified_allergy_signals: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)
    physiological_context: I8GovernedPhysiologicalContext | None = None
    context_refs: list[dict[str, Any]] = field(default_factory=list)


def _json_values(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return [str(raw)[:128]]
    if isinstance(parsed, list):
        return [str(x)[:128] for x in parsed if x]
    if isinstance(parsed, dict):
        text = parsed.get("value") or parsed.get("label") or parsed.get("name")
        return [str(text)[:128]] if text else []
    return [str(parsed)[:128]]


def load_trusted_context(db: Session, user_id: int) -> I8TrustedContext:
    ctx = I8TrustedContext(user_id=user_id)

    for row in (
        db.query(models.UserProfileFact)
        .filter(models.UserProfileFact.user_id == user_id, models.UserProfileFact.fact_type == "allergy")
        .all()
    ):
        for val in _json_values(row.value_json):
            ctx.allergies.append(val)
            ctx.context_refs.append({"ref_type": "user_profile_fact", "ref_id": row.id})

    for row in (
        db.query(models.KcUserFact)
        .filter(models.KcUserFact.user_id == user_id, models.KcUserFact.fact_type == "allergy")
        .all()
    ):
        if row.verified_by:
            continue
        for val in _json_values(row.value_json):
            ctx.unverified_allergy_signals.append(val)

    for row in (
        db.query(models.UserRestriction)
        .filter(models.UserRestriction.user_id == user_id, models.UserRestriction.status == "active")
        .all()
    ):
        ctx.restrictions.append(row.title[:128])
        ctx.context_refs.append({"ref_type": "user_restriction", "ref_id": row.id})

    for row in (
        db.query(models.UserGoal)
        .filter(models.UserGoal.user_id == user_id, models.UserGoal.status == "active")
        .all()
    ):
        ctx.goals.append(row.title[:128])
        ctx.context_refs.append({"ref_type": "user_goal", "ref_id": row.id})

    for row in (
        db.query(models.UserCondition, models.MedicalCondition)
        .join(models.MedicalCondition, models.UserCondition.condition_id == models.MedicalCondition.id)
        .filter(models.UserCondition.user_id == user_id)
        .all()
    ):
        _uc, cond = row
        ctx.conditions.append(cond.name[:128])

    for row in (
        db.query(models.UserMedication, models.Medication)
        .join(models.Medication, models.UserMedication.medication_id == models.Medication.id)
        .filter(models.UserMedication.user_id == user_id)
        .all()
    ):
        _um, med = row
        ctx.medications.append(med.name[:128])

    ctx.physiological_context = get_i8_governed_context_projection(db, account_user_id=user_id)
    ctx.context_refs.extend(projection_context_refs(ctx.physiological_context))

    return ctx
