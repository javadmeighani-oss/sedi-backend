"""I10 notification decision ledger — bounded evidence only."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.policy_types import I10DecisionValue, I10PrivacyClass


class I10DecisionLedgerError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def record_notification_decision(
    db: Session,
    *,
    candidate: I10NotificationCandidate,
    decision: I10DecisionValue,
    reason_code: str,
    recipient_kind: Optional[str] = None,
    privacy_class: Optional[I10PrivacyClass] = None,
    notification_id: Optional[int] = None,
    commit: bool = True,
) -> models.I10NotificationDecision:
    """Persist a bounded policy decision row (idempotent per occurrence triple)."""
    existing = (
        db.query(models.I10NotificationDecision)
        .filter(
            models.I10NotificationDecision.candidate_key == candidate.candidate_key,
            models.I10NotificationDecision.recipient_user_id == candidate.recipient_user_id,
            models.I10NotificationDecision.health_subject_id == candidate.health_subject_id,
        )
        .first()
    )
    privacy_value = (privacy_class or candidate.privacy_hint).value
    if existing is not None:
        existing.decision = decision.value
        existing.reason_code = reason_code
        existing.priority = candidate.priority_hint
        existing.privacy_class = privacy_value
        existing.provenance_refs_json = candidate.provenance_refs_json()
        existing.valid_from = candidate.valid_from
        existing.expires_at = candidate.expires_at
        if notification_id is not None:
            existing.notification_id = notification_id
        row = existing
    else:
        row = models.I10NotificationDecision(
            candidate_key=candidate.candidate_key,
            health_subject_id=candidate.health_subject_id,
            recipient_user_id=candidate.recipient_user_id,
            source_owner=candidate.source_owner,
            source_type=candidate.source_type,
            source_id=candidate.source_id,
            source_version=candidate.source_version,
            semantic_family=candidate.semantic_family.value,
            decision=decision.value,
            reason_code=reason_code,
            priority=candidate.priority_hint,
            privacy_class=privacy_value,
            provenance_refs_json=candidate.provenance_refs_json(),
            valid_from=candidate.valid_from,
            expires_at=candidate.expires_at,
            notification_id=notification_id,
        )
        db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def link_decision_to_notification(
    db: Session,
    *,
    decision_id: int,
    notification_id: int,
    commit: bool = True,
) -> models.I10NotificationDecision:
    row = db.query(models.I10NotificationDecision).filter(models.I10NotificationDecision.id == decision_id).first()
    if row is None:
        raise I10DecisionLedgerError("DECISION_NOT_FOUND")
    row.notification_id = notification_id
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row
