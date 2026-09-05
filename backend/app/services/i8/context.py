"""Read-only trusted user context for I8 decision graph."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.i8_projection_service import (
    I8GovernedPhysiologicalContext,
    get_i8_governed_context_projection,
    projection_context_refs,
)

# Reuse Gate2 list_lifestyle_events default (gate2_data_service.list_lifestyle_events limit=50).
GATE2_LIFESTYLE_EVENT_LIST_LIMIT = 50
# Match I8 knowledge_bridge / I5 MAX_PERSONALIZATION_TERMS_PER_CATEGORY slice pattern.
I8_PERSONAL_CONTEXT_TERM_SLICE = 8
_COMPACT_VALUE_MAX = 64
_HABIT_NAME_MAX = 128
_EVENT_TYPE_MAX = 64

# Soft-delete + non-current statuses (Gate2 HabitCreateIn / delete_habit).
_HABIT_EXCLUDED_STATUSES = frozenset({"inactive", "completed"})


@dataclass(frozen=True)
class I8HabitContextFact:
    habit_id: int
    name: str
    frequency: Optional[str] = None
    target_compact: Optional[str] = None
    status: str = "active"


@dataclass(frozen=True)
class I8LifestyleEventContextFact:
    event_id: int
    event_type: str
    value_compact: Optional[str] = None
    occurred_at: Optional[str] = None
    source: Optional[str] = None


@dataclass
class I8TrustedContext:
    user_id: int
    allergies: list[str] = field(default_factory=list)
    unverified_allergy_signals: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)
    habits: list[I8HabitContextFact] = field(default_factory=list)
    lifestyle_events: list[I8LifestyleEventContextFact] = field(default_factory=list)
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


def _compact_json_value(raw: str | None) -> Optional[str]:
    """Bounded fail-safe compact representation — no raw dump, no notes."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        text = str(raw).strip()
        return text[:_COMPACT_VALUE_MAX] if text else None
    if isinstance(parsed, dict):
        for key in ("value", "label", "name", "target", "amount"):
            if parsed.get(key) is not None:
                return str(parsed[key])[:_COMPACT_VALUE_MAX]
        # Avoid dumping entire dict — take first scalar leaf only.
        for v in parsed.values():
            if isinstance(v, (str, int, float, bool)):
                return str(v)[:_COMPACT_VALUE_MAX]
        return None
    if isinstance(parsed, list):
        if not parsed:
            return None
        return str(parsed[0])[:_COMPACT_VALUE_MAX]
    return str(parsed)[:_COMPACT_VALUE_MAX]


def _dt_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def _load_habits(db: Session, user_id: int, ctx: I8TrustedContext) -> None:
    """Reuse Gate2 list_habits validity (valid_to) + exclude inactive/completed."""
    now = datetime.utcnow()
    rows = (
        db.query(models.UserHabit)
        .filter(
            models.UserHabit.user_id == user_id,
            (models.UserHabit.valid_to.is_(None)) | (models.UserHabit.valid_to > now),
            models.UserHabit.status.notin_(tuple(_HABIT_EXCLUDED_STATUSES)),
        )
        .order_by(models.UserHabit.updated_at.desc())
        .all()
    )
    for row in rows:
        name = (row.name or "").strip()[:_HABIT_NAME_MAX]
        if not name:
            continue
        ctx.habits.append(
            I8HabitContextFact(
                habit_id=int(row.id),
                name=name,
                frequency=(row.frequency[:64] if row.frequency else None),
                target_compact=_compact_json_value(row.target_json),
                status=(row.status or "active")[:32],
            )
        )
        ctx.context_refs.append({"ref_type": "user_habit", "ref_id": int(row.id)})


def _load_lifestyle_events(db: Session, user_id: int, ctx: I8TrustedContext) -> None:
    """Reuse Gate2 list_lifestyle_events bound/order (occurred_at desc, limit=50)."""
    rows = (
        db.query(models.UserLifestyleEvent)
        .filter(models.UserLifestyleEvent.user_id == user_id)
        .order_by(models.UserLifestyleEvent.occurred_at.desc())
        .limit(GATE2_LIFESTYLE_EVENT_LIST_LIMIT)
        .all()
    )
    for row in rows:
        event_type = (row.event_type or "").strip()[:_EVENT_TYPE_MAX]
        if not event_type:
            continue
        ctx.lifestyle_events.append(
            I8LifestyleEventContextFact(
                event_id=int(row.id),
                event_type=event_type,
                value_compact=_compact_json_value(row.value_json),
                occurred_at=_dt_iso(row.occurred_at),
                source=(row.source[:32] if row.source else None),
            )
        )
        ctx.context_refs.append({"ref_type": "user_lifestyle_event", "ref_id": int(row.id)})


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

    _load_habits(db, user_id, ctx)
    _load_lifestyle_events(db, user_id, ctx)

    ctx.physiological_context = get_i8_governed_context_projection(db, account_user_id=user_id)
    ctx.context_refs.extend(projection_context_refs(ctx.physiological_context))

    return ctx
