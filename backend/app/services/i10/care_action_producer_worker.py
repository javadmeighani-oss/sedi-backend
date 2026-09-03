"""I10-B15 I8 CARE_ACTION producer → CaregiverNotificationIntent → B06.

Produces caregiver CARE_ACTION for MANAGED (unlinked) and SELF HealthSubjects
when a governed I8 action is explicitly bound via context_refs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.services.i10.care_action_copy import (
    build_care_action_metadata,
    build_care_action_occurrence_key,
    render_care_action_body,
)
from backend.app.services.i10.care_action_eligibility import is_managed_care_action_eligible
from backend.app.services.i10.care_digest_producer_worker import resolve_subject_owner_user_id
from backend.app.services.i10.caregiver_delivery_intent import create_i10_caregiver_delivery_intent
from backend.app.services.i10.caregiver_delivery_worker import process_caregiver_delivery_intent
from backend.app.services.i10.managed_i8_action_binding import (
    load_active_care_action_subject,
    resolve_action_health_subject_id,
)
from backend.app.services.i10.policy_types import I10NotificationScope, I10PrivacyClass, I10SemanticFamily
from backend.app.services.i10.recipient_eligibility import evaluate_recipient_eligibility
from backend.app.services.section10 import feature_flags

logger = logging.getLogger(__name__)


def _authorized_care_action_recipients(
    db: Session,
    *,
    health_subject_id: int,
) -> list[int]:
    accesses = (
        db.query(models.AccountHealthSubjectAccess)
        .filter(
            models.AccountHealthSubjectAccess.health_subject_id == health_subject_id,
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
            models.AccountHealthSubjectAccess.access_role.in_(("CAREGIVER", "MANAGER")),
        )
        .order_by(models.AccountHealthSubjectAccess.account_user_id.asc())
        .all()
    )
    subject = db.query(models.HealthSubject).filter(models.HealthSubject.id == health_subject_id).first()
    recipients: list[int] = []
    seen: set[int] = set()
    for access in accesses:
        rid = access.account_user_id
        if rid in seen:
            continue
        seen.add(rid)
        if subject is not None and subject.linked_user_id == rid:
            continue
        ev = evaluate_recipient_eligibility(
            db,
            health_subject_id=health_subject_id,
            recipient_user_id=rid,
            notification_scope=I10NotificationScope.CARE_ACTION,
            include_delivery_readiness=False,
        )
        if ev.eligible:
            recipients.append(rid)
    return recipients


def _plan_user_authorized_for_subject(
    db: Session,
    *,
    plan: models.I8OperationalPlan,
    subject: models.HealthSubject,
) -> bool:
    """I8 plan Account must be the SELF linked user or the MANAGED subject's owner."""
    if subject.linked_user_id is not None:
        return int(plan.user_id) == int(subject.linked_user_id)
    owner_id = resolve_subject_owner_user_id(db, subject.id)
    return owner_id is not None and int(plan.user_id) == int(owner_id)


def list_eligible_managed_care_actions(
    db: Session,
    *,
    health_subject_id: int,
    now: datetime,
) -> list[tuple[models.I8OperationalPlanAction, models.I8OperationalPlan]]:
    """Eligible governed I8 actions bound to this HealthSubject (SELF or MANAGED)."""
    subject = load_active_care_action_subject(db, health_subject_id)
    if subject is None:
        return []
    when = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    rows = (
        db.query(models.I8OperationalPlanAction, models.I8OperationalPlan)
        .join(
            models.I8OperationalPlan,
            models.I8OperationalPlan.id == models.I8OperationalPlanAction.plan_id,
        )
        .filter(
            models.I8OperationalPlanAction.status == "ACTIVE",
            models.I8OperationalPlan.status == "ACTIVE",
        )
        .order_by(models.I8OperationalPlanAction.id.asc())
        .all()
    )
    eligible: list[tuple[models.I8OperationalPlanAction, models.I8OperationalPlan]] = []
    for action, plan in rows:
        bound_subject = resolve_action_health_subject_id(db, action)
        if bound_subject != health_subject_id:
            continue
        if not _plan_user_authorized_for_subject(db, plan=plan, subject=subject):
            continue
        if is_managed_care_action_eligible(action, plan, now=when):
            eligible.append((action, plan))
    return eligible


def create_care_action_intents_for_action(
    db: Session,
    *,
    action: models.I8OperationalPlanAction,
    health_subject_id: int,
    commit: bool = True,
) -> list[models.CaregiverNotificationIntent]:
    owner_id = resolve_subject_owner_user_id(db, health_subject_id)
    if owner_id is None:
        return []
    body = render_care_action_body(action)
    metadata = build_care_action_metadata(action, health_subject_id=health_subject_id, body=body)
    valid_from_iso = action.valid_from.isoformat() if action.valid_from else str(action.id)
    occurrence = build_care_action_occurrence_key(
        health_subject_id=health_subject_id,
        action_id=int(action.id),
        valid_from_iso=valid_from_iso,
    )
    created: list[models.CaregiverNotificationIntent] = []
    for recipient_id in _authorized_care_action_recipients(db, health_subject_id=health_subject_id):
        intent = create_i10_caregiver_delivery_intent(
            db,
            owner_user_id=owner_id,
            health_subject_id=health_subject_id,
            recipient_user_id=recipient_id,
            notification_scope=I10NotificationScope.CARE_ACTION,
            occurrence_key=occurrence,
            semantic_family=I10SemanticFamily.CARE_ACTION,
            privacy_class=I10PrivacyClass.HEALTH_SENSITIVE,
            source_entity_type=metadata["source_entity_type"],
            source_entity_id=int(action.id),
            payload_metadata=metadata,
            commit=commit,
        )
        created.append(intent)
    return created


def run_care_action_producer_for_subject(
    db: Session,
    *,
    health_subject_id: int,
    when: Optional[datetime] = None,
    deliver: bool = False,
    commit: bool = True,
) -> dict:
    if not feature_flags.i10_care_action_producer_enabled():
        return {"status": "dormant", "actions": 0, "intents": 0}

    now = when or datetime.now(timezone.utc)
    actions = list_eligible_managed_care_actions(db, health_subject_id=health_subject_id, now=now)
    intents: list[models.CaregiverNotificationIntent] = []
    for action, _plan in actions:
        intents.extend(
            create_care_action_intents_for_action(
                db,
                action=action,
                health_subject_id=health_subject_id,
                commit=commit,
            )
        )
    delivered = 0
    if deliver and feature_flags.i10_care_network_delivery_enabled():
        for intent in intents:
            if intent.status != "pending":
                continue
            outcome = process_caregiver_delivery_intent(db, intent, commit=commit)
            if outcome.get("status") == "processed":
                delivered += 1
    return {
        "status": "ok",
        "actions": len(actions),
        "intents": len(intents),
        "delivered": delivered,
    }


def run_care_action_producer_scan(
    db: Session,
    *,
    now: Optional[datetime] = None,
    limit: int = 100,
    deliver: bool = False,
) -> dict:
    if not feature_flags.i10_care_action_producer_enabled():
        return {"processed": 0, "dormant": True}

    rows = (
        db.query(models.HealthSubject.id)
        .join(
            models.AccountHealthSubjectAccess,
            models.AccountHealthSubjectAccess.health_subject_id == models.HealthSubject.id,
        )
        .filter(
            models.HealthSubject.status == "active",
            models.AccountHealthSubjectAccess.access_role == "CAREGIVER",
            models.AccountHealthSubjectAccess.is_active.is_(True),
            models.AccountHealthSubjectAccess.revoked_at.is_(None),
        )
        .distinct()
        .order_by(models.HealthSubject.id.asc())
        .limit(limit)
        .all()
    )
    summary = {"processed": 0, "actions": 0, "intents": 0, "delivered": 0}
    for (subject_id,) in rows:
        outcome = run_care_action_producer_for_subject(
            db, health_subject_id=int(subject_id), now=now, deliver=deliver, commit=True
        )
        summary["processed"] += 1
        summary["actions"] += outcome.get("actions", 0)
        summary["intents"] += outcome.get("intents", 0)
        summary["delivered"] += outcome.get("delivered", 0)
    return summary
