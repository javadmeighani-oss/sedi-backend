"""I8 proactive evaluation ledger persistence (PD-I8-04A)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app import models

UQ_EVAL_USER_IDENTITY = "uq_i8_eval_user_identity"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_eval_identity_integrity_error(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    diag = getattr(orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name == UQ_EVAL_USER_IDENTITY:
        return True
    blob = " ".join(str(part) for part in (exc, orig, diag, constraint_name) if part is not None).lower()
    return UQ_EVAL_USER_IDENTITY.lower() in blob or (
        "i8_proactive_evaluations" in blob
        and "unique" in blob
        and "evaluation_identity_key" in blob
    )


class I8ProactiveEvaluationRepository:
    def get_by_identity(
        self,
        db: Session,
        *,
        user_id: int,
        evaluation_identity_key: str,
    ) -> Optional[models.I8ProactiveEvaluation]:
        return (
            db.query(models.I8ProactiveEvaluation)
            .filter(
                models.I8ProactiveEvaluation.user_id == user_id,
                models.I8ProactiveEvaluation.evaluation_identity_key == evaluation_identity_key,
            )
            .first()
        )

    def claim_or_get(
        self,
        db: Session,
        *,
        user_id: int,
        trigger_family: str,
        evaluation_identity_key: str,
        trace_id: str | None = None,
    ) -> tuple[models.I8ProactiveEvaluation, str]:
        """Claim evaluation identity or return existing row.

        Returns (row, claim_result):
        claimed | reused_completed | reused_in_progress | reused_terminal | reopened_retryable
        """
        existing = self.get_by_identity(
            db, user_id=user_id, evaluation_identity_key=evaluation_identity_key
        )
        if existing is not None:
            return self._handle_existing(db, existing)

        row = models.I8ProactiveEvaluation(
            user_id=user_id,
            trigger_family=trigger_family,
            evaluation_identity_key=evaluation_identity_key,
            lifecycle_status="IN_PROGRESS",
            outcome=None,
            trace_id=trace_id,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            return row, "claimed"
        except IntegrityError as exc:
            if not _is_eval_identity_integrity_error(exc):
                raise
            raced = self.get_by_identity(
                db, user_id=user_id, evaluation_identity_key=evaluation_identity_key
            )
            if raced is None:
                raise
            return self._handle_existing(db, raced)

    def _handle_existing(
        self,
        db: Session,
        row: models.I8ProactiveEvaluation,
    ) -> tuple[models.I8ProactiveEvaluation, str]:
        status = row.lifecycle_status
        if status == "COMPLETED":
            return row, "reused_completed"
        if status == "FAILED_TERMINAL":
            return row, "reused_terminal"
        if status == "IN_PROGRESS":
            return row, "reused_in_progress"
        if status == "FAILED_RETRYABLE":
            row.lifecycle_status = "IN_PROGRESS"
            row.outcome = None
            row.plan_id = None
            row.action_id = None
            row.completed_at = None
            row.updated_at = _utc_now()
            db.flush()
            return row, "reopened_retryable"
        return row, "reused_in_progress"

    def mark_completed(
        self,
        db: Session,
        row: models.I8ProactiveEvaluation,
        *,
        outcome: str,
        plan_id: int | None = None,
        action_id: int | None = None,
    ) -> models.I8ProactiveEvaluation:
        row.lifecycle_status = "COMPLETED"
        row.outcome = outcome
        row.plan_id = plan_id
        row.action_id = action_id
        row.completed_at = _utc_now()
        row.updated_at = row.completed_at
        db.flush()
        return row

    def mark_failed(
        self,
        db: Session,
        row: models.I8ProactiveEvaluation,
        *,
        lifecycle_status: str,
    ) -> models.I8ProactiveEvaluation:
        if lifecycle_status not in {"FAILED_RETRYABLE", "FAILED_TERMINAL"}:
            raise ValueError("INVALID_FAILURE_LIFECYCLE")
        row.lifecycle_status = lifecycle_status
        row.outcome = None
        row.plan_id = None
        row.action_id = None
        row.completed_at = _utc_now()
        row.updated_at = row.completed_at
        db.flush()
        return row
