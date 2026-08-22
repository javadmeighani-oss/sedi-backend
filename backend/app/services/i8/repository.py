"""I8 operational plan/action repository — data access only."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models


class I8OperationalRepository:
    def get_active_plan(
        self,
        db: Session,
        *,
        user_id: int,
        user_local_date: date,
    ) -> Optional[models.I8OperationalPlan]:
        return (
            db.query(models.I8OperationalPlan)
            .filter(
                models.I8OperationalPlan.user_id == user_id,
                models.I8OperationalPlan.user_local_date == user_local_date,
                models.I8OperationalPlan.status == "ACTIVE",
            )
            .first()
        )

    def get_plan_by_idempotency(
        self,
        db: Session,
        *,
        user_id: int,
        plan_idempotency_key: str,
    ) -> Optional[models.I8OperationalPlan]:
        return (
            db.query(models.I8OperationalPlan)
            .filter(
                models.I8OperationalPlan.user_id == user_id,
                models.I8OperationalPlan.plan_idempotency_key == plan_idempotency_key,
            )
            .first()
        )

    def get_action_by_idempotency(
        self,
        db: Session,
        *,
        plan_id: int,
        action_idempotency_key: str,
    ) -> Optional[models.I8OperationalPlanAction]:
        return (
            db.query(models.I8OperationalPlanAction)
            .filter(
                models.I8OperationalPlanAction.plan_id == plan_id,
                models.I8OperationalPlanAction.action_idempotency_key == action_idempotency_key,
            )
            .first()
        )

    def list_actions_for_plan(
        self,
        db: Session,
        *,
        user_id: int,
        plan_id: int,
    ) -> list[models.I8OperationalPlanAction]:
        return (
            db.query(models.I8OperationalPlanAction)
            .filter(
                models.I8OperationalPlanAction.user_id == user_id,
                models.I8OperationalPlanAction.plan_id == plan_id,
            )
            .order_by(models.I8OperationalPlanAction.id.asc())
            .all()
        )

    def create_plan(
        self,
        db: Session,
        *,
        user_id: int,
        user_local_date: date,
        timezone_snapshot: str,
        generation_mode: str,
        plan_idempotency_key: str,
        valid_from: datetime,
        valid_until: datetime,
        expires_at: datetime,
        trace_id: str | None = None,
        proactive_evaluation_key: str | None = None,
    ) -> models.I8OperationalPlan:
        row = models.I8OperationalPlan(
            user_id=user_id,
            user_local_date=user_local_date,
            timezone_snapshot=timezone_snapshot,
            status="ACTIVE",
            generation_mode=generation_mode,
            plan_idempotency_key=plan_idempotency_key,
            proactive_evaluation_key=proactive_evaluation_key,
            valid_from=valid_from,
            valid_until=valid_until,
            expires_at=expires_at,
            trace_id=trace_id,
        )
        db.add(row)
        db.flush()
        return row

    def create_action(
        self,
        db: Session,
        *,
        user_id: int,
        plan_id: int,
        action_domain: str,
        action_type: str,
        action_idempotency_key: str,
        summary_text: str,
        presentation_json: str,
        knowledge_refs_json: str,
        safety_state: str,
        valid_from: datetime,
        valid_until: datetime,
        expires_at: datetime,
        clarification_required: bool = False,
        context_refs_json: str | None = None,
        advisory_importance: str | None = None,
        trace_id: str | None = None,
        proactive_evaluation_key: str | None = None,
    ) -> models.I8OperationalPlanAction:
        row = models.I8OperationalPlanAction(
            plan_id=plan_id,
            user_id=user_id,
            action_domain=action_domain,
            action_type=action_type,
            status="ACTIVE",
            action_idempotency_key=action_idempotency_key,
            summary_text=summary_text,
            presentation_json=presentation_json,
            knowledge_refs_json=knowledge_refs_json,
            context_refs_json=context_refs_json,
            advisory_importance=advisory_importance,
            safety_state=safety_state,
            clarification_required=clarification_required,
            valid_from=valid_from,
            valid_until=valid_until,
            expires_at=expires_at,
            trace_id=trace_id,
            proactive_evaluation_key=proactive_evaluation_key,
        )
        db.add(row)
        db.flush()
        return row

    def mark_plan_status(
        self,
        db: Session,
        plan: models.I8OperationalPlan,
        status: str,
        *,
        superseded_by_plan_id: int | None = None,
    ) -> None:
        plan.status = status
        if superseded_by_plan_id is not None:
            plan.superseded_by_plan_id = superseded_by_plan_id
        db.flush()
