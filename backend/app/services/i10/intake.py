"""I10 canonical intake/enqueue boundary — candidate → policy → ledger → NotificationBuilder."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.i10.authorization import (
    I10AuthorizationError,
    validate_recipient_notification_authorization,
)
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.canonical_policy import evaluate_i10_canonical_policy
from backend.app.services.i10.decision_ledger import link_decision_to_notification, record_notification_decision
from backend.app.services.i10.policy_types import I10DecisionValue, I10PrivacyClass, I10RecipientKind
from backend.app.services.notification_engine import NotificationBuilder

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class I10IntakeResult:
    decision: I10DecisionValue
    reason_code: str
    decision_id: Optional[int]
    notification_id: Optional[int]
    recipient_kind: Optional[str]


def evaluate_foundation_policy(
    *,
    candidate: I10NotificationCandidate,
    authorized: bool,
) -> tuple[I10DecisionValue, str]:
    """Legacy B01 hook — authorization-only; canonical policy runs in enqueue."""
    if not authorized:
        return I10DecisionValue.SUPPRESS, "AUTHORIZATION_DENIED"
    if candidate.expires_at is not None:
        from datetime import datetime, timezone

        if candidate.expires_at <= datetime.now(timezone.utc):
            return I10DecisionValue.EXPIRE, "CANDIDATE_EXPIRED"
    return I10DecisionValue.SEND, "FOUNDATION_SEND"


def enqueue_i10_notification(
    db: Session,
    *,
    candidate: I10NotificationCandidate,
    payload: NotificationPayload,
    check_dedupe: bool = True,
) -> I10IntakeResult:
    """Canonical I10 intake seam for future producers.

    Flow: validate candidate → authorization → foundation policy → decision ledger
    → NotificationBuilder.persist (existing Gate4/delivery stack).
    """
    try:
        recipient_kind = validate_recipient_notification_authorization(
            db,
            health_subject_id=candidate.health_subject_id,
            recipient_user_id=candidate.recipient_user_id,
            notification_scope=candidate.notification_scope,
        )
        authorized = True
    except I10AuthorizationError as exc:
        recipient_kind = None
        authorized = False
        decision, reason = I10DecisionValue.SUPPRESS, exc.code
        decision_row = record_notification_decision(
            db,
            candidate=candidate,
            decision=decision,
            reason_code=reason,
            privacy_class=candidate.privacy_hint,
            commit=True,
        )
        logger.info(
            "[I10] suppressed candidate=%s subject=%s recipient=%s reason=%s",
            candidate.candidate_key,
            candidate.health_subject_id,
            candidate.recipient_user_id,
            reason,
        )
        return I10IntakeResult(
            decision=decision,
            reason_code=reason,
            decision_id=int(decision_row.id),
            notification_id=None,
            recipient_kind=None,
        )

    decision, reason = evaluate_foundation_policy(candidate=candidate, authorized=authorized)
    if decision == I10DecisionValue.SEND:
        policy_outcome = evaluate_i10_canonical_policy(
            db,
            candidate=candidate,
            payload_metadata=payload.metadata,
            notification_type=payload.type,
            channel=str((payload.metadata or {}).get("channel") or "push"),
        )
        decision = policy_outcome.decision
        reason = policy_outcome.reason_code
        if policy_outcome.defer_until is not None:
            payload.scheduled_for = policy_outcome.defer_until.replace(tzinfo=None)

    decision_row = record_notification_decision(
        db,
        candidate=candidate,
        decision=decision,
        reason_code=reason,
        recipient_kind=recipient_kind.value if recipient_kind else None,
        privacy_class=candidate.privacy_hint,
        commit=True,
    )

    if decision not in (I10DecisionValue.SEND, I10DecisionValue.DEFER):
        return I10IntakeResult(
            decision=decision,
            reason_code=reason,
            decision_id=int(decision_row.id),
            notification_id=None,
            recipient_kind=recipient_kind.value if recipient_kind else None,
        )

    if payload.user_id != candidate.recipient_user_id:
        raise ValueError("I10_RECIPIENT_PAYLOAD_MISMATCH")

    payload.health_subject_id = candidate.health_subject_id
    payload.semantic_family = candidate.semantic_family.value
    payload.recipient_kind = recipient_kind.value if recipient_kind else I10RecipientKind.SELF.value
    payload.privacy_class = candidate.privacy_hint.value
    payload.i10_policy_decision_id = int(decision_row.id)
    payload.metadata = {
        **(payload.metadata or {}),
        "i10_canonical_policy_applied": True,
        "i10_policy_reason": reason,
    }

    builder = NotificationBuilder(db)
    notification = builder.persist(payload, check_dedupe=check_dedupe)
    if notification is None:
        return I10IntakeResult(
            decision=I10DecisionValue.SUPPRESS,
            reason_code="DEDUPE_OR_POLICY_SUPPRESSED",
            decision_id=int(decision_row.id),
            notification_id=None,
            recipient_kind=recipient_kind.value if recipient_kind else None,
        )

    link_decision_to_notification(
        db,
        decision_id=int(decision_row.id),
        notification_id=notification.id,
        commit=True,
    )
    return I10IntakeResult(
        decision=decision,
        reason_code=reason,
        decision_id=int(decision_row.id),
        notification_id=notification.id,
        recipient_kind=recipient_kind.value if recipient_kind else None,
    )


def future_i8_semantic_envelope_to_candidate(envelope: dict[str, Any]) -> None:
    """B01 placeholder — I8 owns meaning; I10 owns interruption policy only."""
    forbidden = {"notification_title", "notification_body", "title", "body"}
    for key in forbidden:
        if key in envelope:
            raise ValueError(f"I10_I8_ENVELOPE_FORBIDDEN_FIELD:{key}")
