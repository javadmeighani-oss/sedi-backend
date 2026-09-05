"""I8-owned exact operational action completion (DONE mapping V1).

DONE completes this exact I8OperationalPlanAction instance only.
Not adherence, not clinical, not future-domain suppression.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models

CANONICAL_TERMINAL_ACTION_STATUS = "COMPLETED"
_COMPLETABLE_STATUS = "ACTIVE"
_TERMINAL_STATUSES = frozenset({"COMPLETED", "SUPERSEDED", "EXPIRED", "CANCELLED", "FAILED"})


class I8ActionCompletionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class I8ActionCompletionResult:
    action_id: int
    status: str
    already_completed: bool
    plan_id: int
    user_id: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def complete_exact_operational_action(
    db: Session,
    *,
    actor_user_id: int,
    action_id: int,
    now: Optional[datetime] = None,
) -> I8ActionCompletionResult:
    """I8 authority: transition exact ACTIVE action → COMPLETED for owning Account only."""
    when = now or _utcnow()
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    action = (
        db.query(models.I8OperationalPlanAction)
        .filter(models.I8OperationalPlanAction.id == int(action_id))
        .first()
    )
    if action is None:
        raise I8ActionCompletionError("ACTION_NOT_FOUND", "Governed I8 action not found.")
    if int(action.user_id) != int(actor_user_id):
        raise I8ActionCompletionError("ACTION_OWNER_MISMATCH", "Action is not owned by actor.")

    plan = (
        db.query(models.I8OperationalPlan)
        .filter(
            models.I8OperationalPlan.id == action.plan_id,
            models.I8OperationalPlan.user_id == actor_user_id,
        )
        .first()
    )
    if plan is None:
        raise I8ActionCompletionError("PLAN_NOT_FOUND", "Governed I8 plan not found for actor.")

    if action.status == CANONICAL_TERMINAL_ACTION_STATUS:
        return I8ActionCompletionResult(
            action_id=int(action.id),
            status=action.status,
            already_completed=True,
            plan_id=int(action.plan_id),
            user_id=int(action.user_id),
        )

    if action.status != _COMPLETABLE_STATUS:
        raise I8ActionCompletionError(
            "ACTION_NOT_COMPLETABLE",
            f"Action status {action.status} cannot be completed.",
        )

    expires = action.expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if when > expires:
            raise I8ActionCompletionError("ACTION_EXPIRED", "Action is past expires_at.")

    action.status = CANONICAL_TERMINAL_ACTION_STATUS
    action.updated_at = when
    db.flush()
    return I8ActionCompletionResult(
        action_id=int(action.id),
        status=action.status,
        already_completed=False,
        plan_id=int(action.plan_id),
        user_id=int(action.user_id),
    )
