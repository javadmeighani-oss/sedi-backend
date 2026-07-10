"""Policy-driven emergency escalation foundation — no real calls."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.section10 import feature_flags

ESCALATION_STATES = frozenset({
    "monitoring",
    "attempting_user_contact",
    "waiting_for_user_response",
    "caregiver_escalation_ready",
    "voice_call_requested",
    "resolved",
    "cancelled",
    "expired",
    "failed",
})


@dataclass(frozen=True)
class EscalationPolicy:
    inactivity_window_minutes: Optional[int]
    notification_attempt_count: Optional[int]
    notification_interval_minutes: Optional[int]
    feedback_grace_period_minutes: Optional[int]
    maximum_caregivers: Optional[int]
    escalation_cooldown_minutes: Optional[int]
    version: str = "v1"

    @classmethod
    def from_env(cls) -> "EscalationPolicy":
        def _opt_int(name: str) -> Optional[int]:
            raw = os.environ.get(name, "").strip()
            if not raw:
                return None
            try:
                return int(raw)
            except ValueError:
                return None

        return cls(
            inactivity_window_minutes=_opt_int("SEDI_ESCALATION_INACTIVITY_WINDOW_MIN"),
            notification_attempt_count=_opt_int("SEDI_ESCALATION_NOTIFICATION_ATTEMPTS"),
            notification_interval_minutes=_opt_int("SEDI_ESCALATION_NOTIFICATION_INTERVAL_MIN"),
            feedback_grace_period_minutes=_opt_int("SEDI_ESCALATION_FEEDBACK_GRACE_MIN"),
            maximum_caregivers=_opt_int("SEDI_ESCALATION_MAX_CAREGIVERS"),
            escalation_cooldown_minutes=_opt_int("SEDI_ESCALATION_COOLDOWN_MIN"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inactivity_window_minutes": self.inactivity_window_minutes,
            "notification_attempt_count": self.notification_attempt_count,
            "notification_interval_minutes": self.notification_interval_minutes,
            "feedback_grace_period_minutes": self.feedback_grace_period_minutes,
            "maximum_caregivers": self.maximum_caregivers,
            "escalation_cooldown_minutes": self.escalation_cooldown_minutes,
            "version": self.version,
        }


def create_escalation_record(
    db: Session,
    owner_user_id: int,
    reason_category: str,
    *,
    policy: Optional[EscalationPolicy] = None,
) -> models.EmergencyEscalationRecord:
    pol = policy or EscalationPolicy.from_env()
    now = datetime.utcnow()
    row = models.EmergencyEscalationRecord(
        owner_user_id=owner_user_id,
        reason_category=reason_category,
        policy_version=pol.version,
        current_state="monitoring",
        attempt_count=0,
        metadata_json=json.dumps({"policy": pol.to_dict()}, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def resolve_emergency_caregiver_order(
    db: Session,
    owner_user_id: int,
) -> List[models.UserCaregiver]:
    rows = (
        db.query(models.UserCaregiver)
        .filter(
            models.UserCaregiver.owner_user_id == owner_user_id,
            models.UserCaregiver.is_active == True,  # noqa: E712
            models.UserCaregiver.notify_emergency == True,  # noqa: E712
        )
        .all()
    )

    def _sort_key(cg: models.UserCaregiver) -> tuple:
        ep = cg.emergency_priority if cg.emergency_priority is not None else 9999
        return (ep, cg.priority, cg.id)

    return sorted(rows, key=_sort_key)


def transition_escalation_state(
    db: Session,
    record: models.EmergencyEscalationRecord,
    new_state: str,
    *,
    resolution_source: Optional[str] = None,
) -> models.EmergencyEscalationRecord:
    if new_state not in ESCALATION_STATES:
        raise ValueError(f"Invalid escalation state: {new_state}")
    record.current_state = new_state
    record.updated_at = datetime.utcnow()
    if new_state in {"resolved", "cancelled", "expired", "failed"}:
        record.resolved_at = datetime.utcnow()
        if resolution_source:
            record.resolution_source = resolution_source
    db.commit()
    db.refresh(record)
    return record


def escalation_runtime_active() -> bool:
    return feature_flags.emergency_escalation_enabled()
