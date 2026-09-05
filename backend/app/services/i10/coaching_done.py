"""Secure I10 coaching DONE path → I8 exact action completion.

Client action_id is never sufficient authority. Notification provenance binds
to the exact I8OperationalPlanAction server-side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i8.action_completion import (
    I8ActionCompletionError,
    complete_exact_operational_action,
)
from backend.app.services.i10.coaching_i10_adapter import (
    COACHING_PRODUCER_OWNER,
    build_coaching_occurrence_key,
)
from backend.app.services.i10.interaction_recorder import (
    InteractionRecordResult,
    record_notification_interaction,
)
from backend.app.services.i10.interaction_vocabulary import (
    CanonicalInteractionVerb,
    resolve_interaction_verb,
)
from backend.app.services.i10.policy_types import I10SemanticFamily


_COACHING_FAMILIES = frozenset(
    {
        I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING.value,
        I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP.value,
        I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP.value,
    }
)


@dataclass(frozen=True)
class CoachingDoneResult:
    interaction: InteractionRecordResult
    action_id: int
    action_status: str
    already_completed: bool


def _parse_positive_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def resolve_i8_action_from_coaching_notification(
    db: Session,
    *,
    notification: models.Notification,
    actor_user_id: int,
    payload: dict[str, Any],
) -> models.I8OperationalPlanAction:
    """Server-side provenance: notification → exact I8 action. Client IDs are advisory only."""
    if int(notification.user_id) != int(actor_user_id):
        raise HTTPException(status_code=403, detail="Notification recipient mismatch.")

    decision = (
        db.query(models.I10NotificationDecision)
        .filter(
            models.I10NotificationDecision.notification_id == notification.id,
            models.I10NotificationDecision.recipient_user_id == actor_user_id,
            models.I10NotificationDecision.source_owner == COACHING_PRODUCER_OWNER,
            models.I10NotificationDecision.decision == "SEND",
        )
        .order_by(models.I10NotificationDecision.id.desc())
        .first()
    )
    if decision is None:
        raise HTTPException(
            status_code=422,
            detail="Notification is not a SEND coaching provenance binding.",
        )
    if decision.semantic_family not in _COACHING_FAMILIES:
        raise HTTPException(status_code=422, detail="Unsupported coaching semantic family.")

    action_id = _parse_positive_int(decision.source_id)
    if action_id is None:
        raise HTTPException(status_code=422, detail="Coaching decision missing action source_id.")

    notif_source_id = _parse_positive_int(notification.source_id)
    if notif_source_id is not None and notif_source_id != action_id:
        raise HTTPException(
            status_code=422,
            detail="Notification/action provenance mismatch.",
        )

    action = (
        db.query(models.I8OperationalPlanAction)
        .filter(models.I8OperationalPlanAction.id == action_id)
        .first()
    )
    if action is None:
        raise HTTPException(status_code=422, detail="Bound I8 action not found.")
    if int(action.user_id) != int(actor_user_id):
        raise HTTPException(status_code=403, detail="I8 action owner mismatch.")

    valid_from_iso = action.valid_from.isoformat() if action.valid_from else str(action.id)
    expected_key = build_coaching_occurrence_key(
        action_id=int(action.id), valid_from_iso=valid_from_iso
    )
    if decision.candidate_key != expected_key:
        raise HTTPException(
            status_code=422,
            detail="Occurrence key does not match bound I8 action.",
        )

    # Client may send forged numeric i8 ids — never redirect completion.
    for key in ("i8_action_id", "action_ref", "plan_action_id"):
        hinted = _parse_positive_int(payload.get(key))
        if hinted is not None and hinted != int(action.id):
            raise HTTPException(
                status_code=422,
                detail="Client action reference does not match notification provenance.",
            )
    meta = payload.get("meta")
    if isinstance(meta, dict):
        hinted = _parse_positive_int(meta.get("i8_action_id"))
        if hinted is not None and hinted != int(action.id):
            raise HTTPException(
                status_code=422,
                detail="Client action reference does not match notification provenance.",
            )

    return action


def handle_coaching_done_for_notification(
    db: Session,
    *,
    notification: models.Notification,
    actor_user_id: int,
    payload: dict[str, Any],
) -> CoachingDoneResult:
    """Authorized DONE path: provenance → I8 completion → ledger record."""
    resolved = resolve_interaction_verb(payload)
    if resolved.verb is not CanonicalInteractionVerb.DONE:
        raise HTTPException(status_code=422, detail="Coaching completion path requires DONE.")

    action = resolve_i8_action_from_coaching_notification(
        db,
        notification=notification,
        actor_user_id=actor_user_id,
        payload=payload,
    )
    try:
        completion = complete_exact_operational_action(
            db,
            actor_user_id=actor_user_id,
            action_id=int(action.id),
        )
    except I8ActionCompletionError as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc

    interaction = record_notification_interaction(
        db,
        notification=notification,
        recipient_user_id=actor_user_id,
        payload=payload,
        domain_completion_authorized=True,
    )
    return CoachingDoneResult(
        interaction=interaction,
        action_id=completion.action_id,
        action_status=completion.status,
        already_completed=completion.already_completed,
    )
