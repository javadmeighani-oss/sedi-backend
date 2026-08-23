"""I8 proactive orchestrator foundation (PD-I8-04A).

Trusted trigger → evaluation ledger claim → Unified I8 Core → durable outcome.
Callable foundation only: no scheduler, Gate2, or I9 runtime wiring.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app.services.i8.constants import (
    PROACTIVE_NO_ACTION_STATUSES,
    PROACTIVE_RETRYABLE_STATUSES,
    PROACTIVE_TERMINAL_STATUSES,
    TRIGGER_FAMILIES,
)
from backend.app.services.i8.contracts import I8OperationalActionResult
from backend.app.services.i8.evaluation_identity import build_evaluation_identity_key
from backend.app.services.i8.evaluation_repository import I8ProactiveEvaluationRepository
from backend.app.services.i8.semantic_envelope import (
    build_semantic_action_envelope,
    envelope_to_presentation_json,
)
from backend.app.services.i8.unified_core import generate_operational_action


@dataclass
class I8ProactiveEvaluationResult:
    status: str
    trigger_family: str
    evaluation_identity_key: str
    lifecycle_status: str
    outcome: Optional[str] = None
    evaluation_id: Optional[int] = None
    plan_id: Optional[int] = None
    action_id: Optional[int] = None
    semantic_envelope: Optional[dict[str, Any]] = None
    core_status: Optional[str] = None
    domain: Optional[str] = None
    summary: str = ""
    reused: bool = False
    knowledge_refs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "trigger_family": self.trigger_family,
            "evaluation_identity_key": self.evaluation_identity_key,
            "lifecycle_status": self.lifecycle_status,
            "outcome": self.outcome,
            "evaluation_id": self.evaluation_id,
            "plan_id": self.plan_id,
            "action_id": self.action_id,
            "semantic_envelope": self.semantic_envelope,
            "core_status": self.core_status,
            "domain": self.domain,
            "summary": self.summary,
            "reused": self.reused,
            "knowledge_refs": list(self.knowledge_refs),
        }


def _classify_core_status(status: str) -> str:
    if status == "ACTION_PERSISTED":
        return "ACTION_CREATED"
    if status in PROACTIVE_NO_ACTION_STATUSES:
        return "NO_ACTION"
    if status in PROACTIVE_TERMINAL_STATUSES:
        return "FAILED_TERMINAL"
    if status in PROACTIVE_RETRYABLE_STATUSES:
        return "FAILED_RETRYABLE"
    return "FAILED_TERMINAL"


def _from_row(
    *,
    row,
    trigger_family: str,
    status: str,
    reused: bool,
    semantic_envelope: dict[str, Any] | None = None,
    core_status: str | None = None,
    domain: str | None = None,
    summary: str = "",
    knowledge_refs: list[dict[str, Any]] | None = None,
) -> I8ProactiveEvaluationResult:
    return I8ProactiveEvaluationResult(
        status=status,
        trigger_family=trigger_family,
        evaluation_identity_key=row.evaluation_identity_key,
        lifecycle_status=row.lifecycle_status,
        outcome=row.outcome,
        evaluation_id=int(row.id) if row.id is not None else None,
        plan_id=int(row.plan_id) if row.plan_id is not None else None,
        action_id=int(row.action_id) if row.action_id is not None else None,
        semantic_envelope=semantic_envelope,
        core_status=core_status,
        domain=domain,
        summary=summary,
        reused=reused,
        knowledge_refs=list(knowledge_refs or []),
    )


def evaluate_proactive_trigger(
    db: Session,
    *,
    user_id: int,
    actor_user_id: int,
    trigger_family: str,
    request: str,
    domain: Optional[str] = None,
    source_owner: Optional[str] = None,
    source_ref: Optional[str] = None,
    schedule_rule_id: Optional[str] = None,
    user_local_date: Optional[date] = None,
    signal_type: Optional[str] = None,
    signal_occurrence_id: Optional[str] = None,
    evaluation_identity_key: Optional[str] = None,
) -> I8ProactiveEvaluationResult:
    """Callable proactive evaluation foundation. Tests may invoke directly."""
    family = (trigger_family or "").strip().casefold()
    if family not in TRIGGER_FAMILIES:
        return I8ProactiveEvaluationResult(
            status="UNSUPPORTED_TRIGGER_FAMILY",
            trigger_family=family or "unknown",
            evaluation_identity_key=evaluation_identity_key or "",
            lifecycle_status="FAILED_TERMINAL",
            summary="Unsupported proactive trigger family.",
        )

    identity = evaluation_identity_key or build_evaluation_identity_key(
        trigger_family=family,
        user_id=user_id,
        source_owner=source_owner,
        source_ref=source_ref,
        schedule_rule_id=schedule_rule_id,
        user_local_date=user_local_date,
        signal_type=signal_type,
        signal_occurrence_id=signal_occurrence_id,
    )

    repo = I8ProactiveEvaluationRepository()
    trace_id = str(uuid.uuid4())
    row, claim = repo.claim_or_get(
        db,
        user_id=user_id,
        trigger_family=family,
        evaluation_identity_key=identity,
        trace_id=trace_id,
    )

    if claim == "reused_completed":
        db.commit()
        return _from_row(
            row=row,
            trigger_family=family,
            status="EVALUATION_REUSED",
            reused=True,
            summary="Completed evaluation reused idempotently.",
        )

    if claim == "reused_terminal":
        db.commit()
        return _from_row(
            row=row,
            trigger_family=family,
            status="EVALUATION_TERMINAL",
            reused=True,
            summary="Terminal evaluation cannot be retried under a new identity.",
        )

    if claim == "reused_in_progress":
        db.commit()
        return _from_row(
            row=row,
            trigger_family=family,
            status="EVALUATION_IN_PROGRESS",
            reused=True,
            summary="Evaluation already in progress for this identity.",
        )

    # claimed or reopened_retryable → single Unified I8 Core (no second engine).
    plan_key = f"proactive:{identity}"
    action_key = f"proactive-action:{identity}"
    core: I8OperationalActionResult = generate_operational_action(
        db,
        user_id=user_id,
        actor_user_id=actor_user_id,
        request=request,
        domain=domain,
        persist=True,
        plan_idempotency_key=plan_key,
        action_idempotency_key=action_key,
        generation_mode="proactive",
        proactive_evaluation_key=identity,
    )

    classified = _classify_core_status(core.status)
    semantic: dict[str, Any] | None = None

    if classified == "ACTION_CREATED":
        if core.persisted and core.action_id is not None:
            semantic = build_semantic_action_envelope(
                user_id=user_id,
                domain=core.domain,
                action_type=f"{core.domain}_suggestion",
                sanitized_presentation_meaning=core.summary or "Governed health action",
                safety_state=core.safety_state,
                knowledge_refs=list(core.knowledge_refs),
                valid_from=core.valid_from,
                valid_until=core.valid_until,
                lifecycle_status="ACTIVE",
                plan_id=core.plan_id,
                action_id=core.action_id,
                evaluation_identity_key=identity,
                applicability_state="SAFE" if core.safety_state == "SAFE" else core.safety_state,
            )
            envelope_to_presentation_json(semantic)
        repo.mark_completed(
            db,
            row,
            outcome="ACTION_CREATED",
            plan_id=core.plan_id,
            action_id=core.action_id,
        )
        db.commit()
        return _from_row(
            row=row,
            trigger_family=family,
            status="ACTION_CREATED",
            reused=False,
            semantic_envelope=semantic,
            core_status=core.status,
            domain=core.domain,
            summary=core.summary,
            knowledge_refs=list(core.knowledge_refs),
        )

    if classified == "NO_ACTION":
        repo.mark_completed(db, row, outcome="NO_ACTION")
        db.commit()
        return _from_row(
            row=row,
            trigger_family=family,
            status="NO_ACTION",
            reused=False,
            core_status=core.status,
            domain=core.domain,
            summary=core.summary or "Legitimate proactive non-action.",
        )

    repo.mark_failed(db, row, lifecycle_status=classified)
    db.commit()
    return _from_row(
        row=row,
        trigger_family=family,
        status=classified,
        reused=False,
        core_status=core.status,
        domain=core.domain,
        summary=core.summary,
    )
