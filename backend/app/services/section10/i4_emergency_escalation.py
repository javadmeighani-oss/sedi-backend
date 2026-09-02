"""I4 → Section10 authoritative emergency escalation persist seam (no I4 re-decision)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i9.health_subject_service import ensure_self_subject_for_account
from backend.app.services.intelligence.contracts import RiskAssessment
from backend.app.services.section10.emergency_escalation_service import EscalationPolicy
from backend.app.services.section10.i4_escalation_provenance import (
    READY_STATE,
    build_i4_escalation_provenance,
    is_authoritative_i4_emergency_assessment,
    new_occurrence_id,
    parse_escalation_metadata,
)
from backend.app.services.section10 import feature_flags

logger = logging.getLogger(__name__)


def _resolve_self_health_subject(
    db: Session,
    authenticated_user_id: int,
    health_subject_id: int,
) -> Optional[models.HealthSubject]:
    subject = (
        db.query(models.HealthSubject)
        .filter(
            models.HealthSubject.id == health_subject_id,
            models.HealthSubject.status == "active",
        )
        .first()
    )
    if subject is None:
        return None
    if subject.linked_user_id != authenticated_user_id:
        return None
    access = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.account_user_id == authenticated_user_id,
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.access_role == "SELF",
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .first()
    )
    if access is None:
        return None
    return subject


def _find_by_occurrence_id(
    db: Session,
    *,
    owner_user_id: int,
    occurrence_id: str,
) -> Optional[models.EmergencyEscalationRecord]:
    rows = (
        db.query(models.EmergencyEscalationRecord)
        .filter(models.EmergencyEscalationRecord.owner_user_id == owner_user_id)
        .order_by(models.EmergencyEscalationRecord.id.asc())
        .all()
    )
    for row in rows:
        meta = parse_escalation_metadata(row.metadata_json)
        if meta.get("occurrence_id") == occurrence_id:
            return row
    return None


def persist_i4_emergency_escalation(
    db: Session,
    *,
    authenticated_user_id: int,
    health_subject_id: int,
    risk_assessment: RiskAssessment,
    occurrence_id: Optional[str] = None,
    commit: bool = True,
) -> Optional[models.EmergencyEscalationRecord]:
    """Persist one I4 EMERGENCY occurrence. Returns None when authority is not met."""
    if not isinstance(authenticated_user_id, int) or authenticated_user_id <= 0:
        return None
    if not isinstance(health_subject_id, int) or health_subject_id <= 0:
        return None
    if not is_authoritative_i4_emergency_assessment(risk_assessment):
        return None
    subject = _resolve_self_health_subject(db, authenticated_user_id, health_subject_id)
    if subject is None:
        return None

    occ_id = occurrence_id or new_occurrence_id()
    existing = _find_by_occurrence_id(
        db, owner_user_id=authenticated_user_id, occurrence_id=occ_id
    )
    if existing is not None:
        return existing

    pol = EscalationPolicy.from_env()
    now = datetime.utcnow()
    provenance = build_i4_escalation_provenance(
        risk_assessment=risk_assessment,
        health_subject_id=int(subject.id),
        occurrence_id=occ_id,
        policy=pol.to_dict(),
    )
    row = models.EmergencyEscalationRecord(
        owner_user_id=authenticated_user_id,
        reason_category=str(risk_assessment.domain.value)[:64],
        policy_version=pol.version,
        current_state=READY_STATE,
        attempt_count=0,
        metadata_json=json.dumps(provenance, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def attempt_i4_emergency_escalation_from_interact(
    db: Session,
    *,
    authenticated_user_id: int,
    risk_assessment: RiskAssessment,
) -> None:
    """Best-effort ledger persist + optional B16. Never raises into the safety response path."""
    if not is_authoritative_i4_emergency_assessment(risk_assessment):
        return

    occurrence_id = new_occurrence_id()
    record: Optional[models.EmergencyEscalationRecord] = None
    for attempt in range(2):
        try:
            subject = ensure_self_subject_for_account(
                db, authenticated_user_id, commit=False
            )
            record = persist_i4_emergency_escalation(
                db,
                authenticated_user_id=authenticated_user_id,
                health_subject_id=int(subject.id),
                risk_assessment=risk_assessment,
                occurrence_id=occurrence_id,
                commit=True,
            )
            break
        except Exception:
            logger.exception("I4_ESCALATION_PERSIST_FAILED")
            try:
                db.rollback()
            except Exception:
                logger.exception("I4_ESCALATION_PERSIST_ROLLBACK_FAILED")
            if attempt == 0:
                continue
            return

    if record is None:
        return

    try:
        hs_id = int(parse_escalation_metadata(record.metadata_json).get("health_subject_id") or 0)
        if hs_id <= 0:
            return
        if feature_flags.i10_care_safety_producer_enabled():
            from backend.app.services.i10.care_safety_producer_worker import (
                run_care_safety_producer_for_subject,
            )

            run_care_safety_producer_for_subject(
                db,
                health_subject_id=hs_id,
                deliver=feature_flags.i10_care_network_delivery_enabled(),
                commit=True,
            )
    except Exception:
        logger.exception("I4_ESCALATION_PRODUCER_FAILED")
        try:
            db.rollback()
        except Exception:
            logger.exception("I4_ESCALATION_PRODUCER_ROLLBACK_FAILED")
