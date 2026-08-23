"""Transactional lifecycle for I8 same-day operational plans."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i8.local_day import LocalDayWindow
from backend.app.services.i8.repository import I8OperationalRepository


class I8OperationalLifecycle:
    def __init__(self, repo: I8OperationalRepository | None = None) -> None:
        self._repo = repo or I8OperationalRepository()

    def ensure_active_plan(
        self,
        db: Session,
        *,
        user_id: int,
        window: LocalDayWindow,
        generation_mode: str,
        plan_idempotency_key: str,
        trace_id: str | None = None,
        proactive_evaluation_key: str | None = None,
    ) -> tuple[models.I8OperationalPlan, bool]:
        """Return (plan, created). Idempotent on plan_idempotency_key."""
        existing = self._repo.get_plan_by_idempotency(
            db, user_id=user_id, plan_idempotency_key=plan_idempotency_key
        )
        if existing is not None:
            return existing, False

        active = self._repo.get_active_plan(
            db, user_id=user_id, user_local_date=window.user_local_date
        )
        prior_active_id = active.id if active is not None else None
        if active is not None:
            self._repo.mark_plan_status(db, active, "SUPERSEDED")
        plan = self._repo.create_plan(
            db,
            user_id=user_id,
            user_local_date=window.user_local_date,
            timezone_snapshot=window.timezone_snapshot,
            generation_mode=generation_mode,
            plan_idempotency_key=plan_idempotency_key,
            valid_from=window.valid_from,
            valid_until=window.valid_until,
            expires_at=window.expires_at,
            trace_id=trace_id,
            proactive_evaluation_key=proactive_evaluation_key,
        )
        if prior_active_id is not None and prior_active_id != plan.id:
            prior = db.query(models.I8OperationalPlan).filter_by(id=prior_active_id).one()
            self._repo.mark_plan_status(
                db,
                prior,
                "SUPERSEDED",
                superseded_by_plan_id=plan.id,
            )
        return plan, True

    def ensure_action(
        self,
        db: Session,
        *,
        user_id: int,
        plan: models.I8OperationalPlan,
        window: LocalDayWindow,
        action_domain: str,
        action_type: str,
        action_idempotency_key: str,
        summary_text: str,
        presentation_json: str,
        knowledge_refs_json: str,
        safety_state: str,
        clarification_required: bool = False,
        context_refs_json: str | None = None,
        trace_id: str | None = None,
        proactive_evaluation_key: str | None = None,
    ) -> tuple[models.I8OperationalPlanAction, bool]:
        existing = self._repo.get_action_by_idempotency(
            db, plan_id=plan.id, action_idempotency_key=action_idempotency_key
        )
        if existing is not None:
            return existing, False
        action = self._repo.create_action(
            db,
            user_id=user_id,
            plan_id=plan.id,
            action_domain=action_domain,
            action_type=action_type,
            action_idempotency_key=action_idempotency_key,
            summary_text=summary_text,
            presentation_json=presentation_json,
            knowledge_refs_json=knowledge_refs_json,
            safety_state=safety_state,
            clarification_required=clarification_required,
            context_refs_json=context_refs_json,
            valid_from=window.valid_from,
            valid_until=window.valid_until,
            expires_at=window.expires_at,
            trace_id=trace_id,
            proactive_evaluation_key=proactive_evaluation_key,
        )
        return action, True
