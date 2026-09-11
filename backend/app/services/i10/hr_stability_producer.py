"""I10 HR stability seams — MAD evidence → canonical I9 status → daily/instability intents.

Distinct from CARE_STATUS_DIGEST. No diagnosis/emergency wording.
DRVS must not mint parallel I10 for the same governed HR transition.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.care_digest_producer_worker import (
    _authorized_recipients,
    resolve_subject_owner_user_id,
)
from backend.app.services.i10.caregiver_delivery_intent import create_i10_caregiver_delivery_intent
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.policy_types import I10NotificationScope, I10PrivacyClass, I10SemanticFamily
from backend.app.services.i10.recipient_eligibility import evaluate_recipient_eligibility
from backend.app.services.i9.hr_stability import (
    CanonicalHrStabilityResult,
    CanonicalHrStabilityStatus,
    evaluate_canonical_hr_stability,
)

logger = logging.getLogger(__name__)

PRODUCER_OWNER = "I10_HR_STABILITY"
FORBIDDEN = ("safe", "healthy", "danger", "emergency", "diagnosis", "critical", "medically")


def build_hr_daily_stability_occurrence_key(*, health_subject_id: int, period_date) -> str:
    return f"i10:hr:daily_stability:{int(health_subject_id)}:{period_date.isoformat()}"


def build_hr_instability_occurrence_key(*, health_subject_id: int, period_date, reason: str) -> str:
    safe_reason = (reason or "changed").replace(" ", "_")[:64]
    return f"i10:hr:instability:{int(health_subject_id)}:{period_date.isoformat()}:{safe_reason}"


def _period_date(when: datetime):
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).date()


def _assert_safe_copy(text: str) -> None:
    lower = text.lower()
    for word in FORBIDDEN:
        if word in lower:
            raise ValueError(f"FORBIDDEN_NOTIFICATION_LANGUAGE:{word}")


def _recipients_for_hr_stability(
    db: Session,
    *,
    health_subject_id: int,
    notification_scope: I10NotificationScope,
) -> list[int]:
    """SELF account (if linked) + authorized CAREGIVER/MANAGER Accounts. No fake OTHER Account."""
    out: list[int] = []
    seen: set[int] = set()
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    if subject is not None and subject.linked_user_id is not None:
        rid = int(subject.linked_user_id)
        ev = evaluate_recipient_eligibility(
            db,
            health_subject_id=health_subject_id,
            recipient_user_id=rid,
            notification_scope=notification_scope,
            include_delivery_readiness=False,
        )
        if ev.eligible:
            out.append(rid)
            seen.add(rid)
    for rid in _authorized_recipients(
        db,
        health_subject_id=health_subject_id,
        notification_scope=notification_scope,
    ):
        if rid not in seen:
            out.append(rid)
            seen.add(rid)
    return out


def _create_intents(
    db: Session,
    *,
    health_subject_id: int,
    notification_scope: I10NotificationScope,
    semantic_family: I10SemanticFamily,
    occurrence_key: str,
    title: str,
    body: str,
    status_value: str,
    reason: str,
    deliver: bool,
    commit: bool,
) -> list[models.CaregiverNotificationIntent]:
    _assert_safe_copy(body)
    owner_id = resolve_subject_owner_user_id(db, health_subject_id)
    metadata = {
        "title": title,
        "body": body,
        "template_key": semantic_family.value.lower(),
        "trigger_reason": semantic_family.value,
        "status": status_value,
        "reason": reason,
        "signal_scope": "heart_rate",
        "authority": "I9_CANONICAL_HR_STABILITY",
        "evidence": "PERSONAL_OBSERVED_BASELINE_V1_MAD",
        "semantic_family": semantic_family.value,
        "privacy_class": I10PrivacyClass.HEALTH_SENSITIVE.value,
        "source_entity_type": PRODUCER_OWNER,
    }
    created: list[models.CaregiverNotificationIntent] = []
    for recipient_id in _recipients_for_hr_stability(
        db,
        health_subject_id=health_subject_id,
        notification_scope=notification_scope,
    ):
        intent = create_i10_caregiver_delivery_intent(
            db,
            owner_user_id=owner_id,
            health_subject_id=health_subject_id,
            recipient_user_id=recipient_id,
            notification_scope=notification_scope,
            occurrence_key=occurrence_key,
            semantic_family=semantic_family,
            privacy_class=I10PrivacyClass.HEALTH_SENSITIVE,
            source_entity_type=PRODUCER_OWNER,
            source_entity_id=None,
            payload_metadata=metadata,
            commit=commit,
        )
        created.append(intent)
        if deliver and intent.status == "pending":
            process_caregiver_delivery_intent(db, intent, commit=commit)
    return created


def emit_hr_stability_i10_for_subject(
    db: Session,
    *,
    health_subject_id: int,
    when: Optional[datetime] = None,
    deliver: bool = False,
    commit: bool = True,
    result: Optional[CanonicalHrStabilityResult] = None,
) -> list[models.CaregiverNotificationIntent]:
    """Evaluate canonical HR status and mint DAILY_STABILITY or INSTABILITY intents."""
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    evaluated = result or evaluate_canonical_hr_stability(
        db, health_subject_id=int(health_subject_id), when=when
    )
    period = _period_date(when)
    created: list[models.CaregiverNotificationIntent] = []

    if evaluated.status == CanonicalHrStabilityStatus.INSUFFICIENT_DATA:
        logger.info(
            "[I10_HR] insufficient hs=%s reason=%s",
            health_subject_id,
            evaluated.reason,
        )
        return []

    if evaluated.status == CanonicalHrStabilityStatus.STABLE:
        created.extend(
            _create_intents(
                db,
                health_subject_id=int(health_subject_id),
                notification_scope=I10NotificationScope.GENERAL_STATUS,
                semantic_family=I10SemanticFamily.HR_DAILY_STABILITY,
                occurrence_key=build_hr_daily_stability_occurrence_key(
                    health_subject_id=int(health_subject_id), period_date=period
                ),
                title="Heart-rate daily stability",
                body=(
                    "Heart-rate pattern for the subject is within their personal observed band today. "
                    "This is observational pattern information only."
                ),
                status_value=evaluated.status.value,
                reason=evaluated.reason,
                deliver=deliver,
                commit=commit,
            )
        )
        return created

    # UNSTABLE_OR_CHANGED
    created.extend(
        _create_intents(
            db,
            health_subject_id=int(health_subject_id),
            notification_scope=I10NotificationScope.DEVICE_STATUS,
            semantic_family=I10SemanticFamily.HR_INSTABILITY,
            occurrence_key=build_hr_instability_occurrence_key(
                health_subject_id=int(health_subject_id),
                period_date=period,
                reason=evaluated.reason,
            ),
            title="Heart-rate pattern change",
                body=(
                    "Heart-rate pattern for the subject differs from their personal observed band. "
                    "Please check on them. This is observational pattern information only."
                ),
            status_value=evaluated.status.value,
            reason=evaluated.reason,
            deliver=deliver,
            commit=commit,
        )
    )
    return created
