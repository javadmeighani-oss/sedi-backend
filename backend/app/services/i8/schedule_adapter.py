"""Thin schedule adapter: TrustedTrigger_V1 → existing proactive orchestrator."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.services.i8.proactive_orchestrator import (
    I8ProactiveEvaluationResult,
    evaluate_proactive_trigger,
)
from backend.app.services.i8.trusted_trigger import (
    TrustedTriggerV1,
    validate_trusted_schedule_trigger,
)

# Fixed, non-clinical prompt seed — Unified I8 Core owns the decision.
_SCHEDULE_REQUEST = "Proactive schedule evaluation."


def adapt_trusted_schedule_trigger(
    db: Session,
    trigger: TrustedTriggerV1,
) -> I8ProactiveEvaluationResult:
    """Validate trusted SCHEDULE trigger and delegate to evaluate_proactive_trigger.

    Contains no health/lifestyle decision logic and does not bypass the 070 ledger.
    """
    trusted = validate_trusted_schedule_trigger(trigger)
    return evaluate_proactive_trigger(
        db,
        user_id=trusted.user_id,
        actor_user_id=trusted.user_id,
        trigger_family="schedule",
        request=_SCHEDULE_REQUEST,
        schedule_rule_id=trusted.schedule_rule_id,
        user_local_date=trusted.user_local_date,
    )
