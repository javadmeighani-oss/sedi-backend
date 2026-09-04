"""Subject-aware I8 trusted context (C04) — actor Account ≠ patient HealthSubject."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i8.context import I8TrustedContext, load_trusted_context
from backend.app.services.i9.health_subject_service import (
    HealthSubjectAccessDenied,
    require_account_subject_access,
)
from backend.app.services.i9.i8_projection_service import (
    get_bounded_context_projection_for_subject,
    projection_context_refs,
)


@dataclass
class I8SubjectTrustedContext:
    """Governed I8 context for an explicit HealthSubject under an actor Account."""

    actor_account_user_id: int
    health_subject_id: int
    subject_kind: str
    linked_user_id: Optional[int]
    conditions: list[str] = field(default_factory=list)
    condition_refs: list[dict[str, Any]] = field(default_factory=list)
    physiological_context: Any = None
    context_refs: list[dict[str, Any]] = field(default_factory=list)
    # Legacy Account-attributed fields — only populated for actor's own SELF subject.
    allergies: list[str] = field(default_factory=list)
    medications: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    restrictions: list[str] = field(default_factory=list)


def load_subject_trusted_context(
    db: Session,
    *,
    actor_account_user_id: int,
    health_subject_id: int,
) -> I8SubjectTrustedContext:
    """Authorize actor→subject, load subject conditions + I9 physio; never substitute actor clinical identity."""
    subject = require_account_subject_access(db, actor_account_user_id, health_subject_id)

    ctx = I8SubjectTrustedContext(
        actor_account_user_id=actor_account_user_id,
        health_subject_id=subject.id,
        subject_kind=subject.subject_kind,
        linked_user_id=subject.linked_user_id,
    )

    for row in (
        db.query(models.HealthSubjectCondition, models.MedicalCondition)
        .join(models.MedicalCondition, models.HealthSubjectCondition.condition_id == models.MedicalCondition.id)
        .filter(
            models.HealthSubjectCondition.health_subject_id == subject.id,
            models.HealthSubjectCondition.status == "active",
        )
        .order_by(models.HealthSubjectCondition.id.asc())
        .all()
    ):
        hsc, cond = row
        ctx.conditions.append(cond.name[:128])
        ctx.condition_refs.append(
            {
                "ref_type": "health_subject_condition",
                "ref_id": hsc.id,
                "health_subject_id": subject.id,
                "source_class": hsc.source_class,
                "verification_state": hsc.verification_state,
            }
        )
        ctx.context_refs.append(
            {
                "ref_type": "health_subject_condition",
                "ref_id": hsc.id,
                "health_subject_id": subject.id,
            }
        )

    # Subject-native physiological projection — no linked_user_id required.
    ctx.physiological_context = get_bounded_context_projection_for_subject(
        db, health_subject_id=subject.id
    )
    ctx.context_refs.extend(projection_context_refs(ctx.physiological_context))
    ctx.context_refs.append({"ref_type": "health_subject", "ref_id": subject.id})

    # Account-only legacy profile (meds/allergies/goals) ONLY when subject is actor's SELF.
    # Never attribute Son Account clinical profile onto Mother HealthSubject.
    is_actor_self = (
        subject.subject_kind == "self"
        and subject.linked_user_id is not None
        and int(subject.linked_user_id) == int(actor_account_user_id)
    )
    if is_actor_self:
        legacy = load_trusted_context(db, actor_account_user_id)
        ctx.allergies = list(legacy.allergies)
        ctx.medications = list(legacy.medications)
        ctx.goals = list(legacy.goals)
        ctx.restrictions = list(legacy.restrictions)
        # Prefer HealthSubjectCondition names; if empty, fall back to legacy UserCondition for SELF only.
        if not ctx.conditions and legacy.conditions:
            ctx.conditions = list(legacy.conditions)

    return ctx


def to_i8_trusted_context_compat(subject_ctx: I8SubjectTrustedContext) -> I8TrustedContext:
    """Adapter for call sites that still expect I8TrustedContext shape.

    user_id is the actor Account (gateway), not patient identity. Patient identity is
    carried via physiological_context.health_subject_id and context_refs.
    """
    return I8TrustedContext(
        user_id=subject_ctx.actor_account_user_id,
        allergies=list(subject_ctx.allergies),
        restrictions=list(subject_ctx.restrictions),
        goals=list(subject_ctx.goals),
        conditions=list(subject_ctx.conditions),
        medications=list(subject_ctx.medications),
        physiological_context=subject_ctx.physiological_context,
        context_refs=list(subject_ctx.context_refs),
    )
