"""I10 care network caregiver delivery worker — canonical I10 intake only."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from backend.app import models
from backend.app.schemas.notification import NotificationPayload
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
    sanitize_notification_context,
)
from backend.app.services.i10.caregiver_delivery_intent import build_i10_occurrence_dedupe_key
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.intake import enqueue_i10_notification
from backend.app.services.i10.policy_types import (
    I10DecisionValue,
    I10NotificationScope,
    I10PrivacyClass,
    I10SemanticFamily,
)
from backend.app.services.i10.recipient_eligibility import evaluate_delivery_eligibility
from backend.app.services.section10 import feature_flags

logger = logging.getLogger(__name__)

_PRIVACY_SAFE_BODIES = {
    I10NotificationScope.GENERAL_STATUS: "A care status update is available.",
    I10NotificationScope.DEVICE_STATUS: "A device status update is available for your care recipient.",
    I10NotificationScope.CARE_ACTION: "A care action may need your attention.",
    I10NotificationScope.SAFETY_ESCALATION: "A safety-related care notification is available.",
    I10NotificationScope.SENSITIVE_HEALTH_DETAIL: "A health-related care notification is available.",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_scope(value: str) -> I10NotificationScope:
    return I10NotificationScope(value)


def _parse_semantic(value: str | None) -> I10SemanticFamily:
    if value:
        return I10SemanticFamily(value)
    return I10SemanticFamily.GENERAL_STATUS


def _parse_privacy(value: str | None) -> I10PrivacyClass:
    if value:
        return I10PrivacyClass(value)
    return I10PrivacyClass.PRIVATE


def _load_payload_metadata(intent: models.CaregiverNotificationIntent) -> dict[str, Any]:
    raw = intent.payload_metadata_json
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _build_delivery_payload(
    intent: models.CaregiverNotificationIntent,
    *,
    candidate_key: str,
    scope: I10NotificationScope,
    candidate: I10NotificationCandidate,
) -> NotificationPayload:
    metadata = _load_payload_metadata(intent)
    body = str(metadata.get("body") or "").strip()
    if not body:
        body = _PRIVACY_SAFE_BODIES.get(scope, "A care network notification is available.")
    title = str(metadata.get("title") or "Care update").strip()[:200]
    context_raw = metadata.get("context")
    context = sanitize_notification_context(context_raw if isinstance(context_raw, dict) else None) or {}
    template_key = metadata.get("template_key") or intent.source_entity_type or "i10_care_network"
    source_type = intent.source_entity_type or "caregiver_delivery"
    source_id = str(intent.source_entity_id or intent.id)
    return NotificationPayload(
        user_id=intent.recipient_user_id,
        type="health_alert",
        title=title,
        body=body,
        priority="normal",
        dedupe_key=candidate_key,
        health_subject_id=intent.health_subject_id,
        semantic_family=candidate.semantic_family.value,
        privacy_class=candidate.privacy_hint.value,
        metadata={
            "data_status": metadata.get("data_status"),
            "trigger_reason": metadata.get("trigger_reason"),
        },
        category=NotificationCategory.DAILY_STATUS.value,
        source_type=NotificationSourceType.DAILY_ROUTINE.value,
        source_id=source_id[:255],
        risk_level=NotificationRiskLevel.INFORMATIONAL.value,
        template_key=str(template_key)[:100],
        context=context,
    )


def process_caregiver_delivery_intent(
    db: Session,
    intent: models.CaregiverNotificationIntent,
    *,
    commit: bool = True,
) -> dict:
    """Process one I10 care-network delivery intent with delivery-time revalidation."""
    if intent.health_subject_id is None or intent.recipient_user_id is None:
        return {"status": "skipped", "reason": "NOT_I10_INTENT"}
    if intent.status in ("processed", "suppressed", "expired", "failed_final"):
        return {"status": "idempotent", "reason": intent.status}
    if intent.status != "pending":
        return {"status": "skipped", "reason": f"STATUS_{intent.status}"}

    if not feature_flags.i10_care_network_delivery_enabled():
        return {"status": "dormant", "reason": "FLAG_OFF"}

    now = _utc_now()
    if intent.expires_at is not None and intent.expires_at <= now:
        intent.status = "expired"
        intent.processed_at = now.replace(tzinfo=None)
        intent.failure_reason = "INTENT_EXPIRED"
        if commit:
            db.commit()
        return {"status": "expired", "reason": "INTENT_EXPIRED"}

    scope = _parse_scope(intent.notification_scope or I10NotificationScope.GENERAL_STATUS.value)
    eligibility = evaluate_delivery_eligibility(
        db,
        health_subject_id=intent.health_subject_id,
        recipient_user_id=intent.recipient_user_id,
        notification_scope=scope,
        user_caregiver_id=intent.caregiver_id,
    )

    if not eligibility.eligible:
        return _finalize_intent(
            db,
            intent,
            status="suppressed",
            reason=eligibility.reason_code,
            commit=commit,
        )

    if not eligibility.delivery_ready:
        return _finalize_intent(
            db,
            intent,
            status="suppressed",
            reason=eligibility.delivery_reason_code or "NOT_DELIVERY_READY",
            commit=commit,
        )

    occurrence = intent.occurrence_key or f"intent-{intent.id}"
    candidate_key = build_i10_occurrence_dedupe_key(
        health_subject_id=intent.health_subject_id,
        recipient_user_id=intent.recipient_user_id,
        occurrence_key=occurrence,
        notification_scope=scope,
    ).replace("i10:care:", "i10:occ:")

    candidate = I10NotificationCandidate(
        candidate_key=candidate_key,
        health_subject_id=intent.health_subject_id,
        recipient_user_id=intent.recipient_user_id,
        notification_scope=scope,
        source_owner="I10_CARE_NETWORK",
        source_type=intent.source_entity_type or "caregiver_delivery",
        source_id=str(intent.id),
        semantic_family=_parse_semantic(intent.semantic_family),
        privacy_hint=_parse_privacy(intent.privacy_class),
        expires_at=intent.expires_at,
        user_caregiver_id=intent.caregiver_id,
    )
    payload = _build_delivery_payload(
        intent,
        candidate_key=candidate_key,
        scope=scope,
        candidate=candidate,
    )

    result = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)

    intent.i10_decision_id = result.decision_id
    intent.notification_id = result.notification_id
    intent.processed_at = now.replace(tzinfo=None)

    if result.decision == I10DecisionValue.SEND and result.notification_id is not None:
        intent.status = "processed"
        intent.failure_reason = None
        outcome = {"status": "processed", "notification_id": result.notification_id}
    else:
        intent.status = "suppressed"
        intent.failure_reason = result.reason_code
        outcome = {"status": "suppressed", "reason": result.reason_code}

    if commit:
        db.commit()
        db.refresh(intent)
    return outcome


def process_pending_caregiver_delivery_intents(
    db: Session,
    *,
    limit: int = 50,
) -> dict:
    """Batch worker entry — processes pending I10 care-network intents."""
    if not feature_flags.i10_care_network_delivery_enabled():
        return {"processed": 0, "dormant": True}

    rows = (
        db.query(models.CaregiverNotificationIntent)
        .filter(
            models.CaregiverNotificationIntent.status == "pending",
            models.CaregiverNotificationIntent.health_subject_id.isnot(None),
            models.CaregiverNotificationIntent.recipient_user_id.isnot(None),
        )
        .order_by(models.CaregiverNotificationIntent.id.asc())
        .limit(limit)
        .all()
    )
    summary = {"processed": 0, "suppressed": 0, "expired": 0, "skipped": 0}
    for row in rows:
        outcome = process_caregiver_delivery_intent(db, row, commit=True)
        key = outcome.get("status", "skipped")
        if key in summary:
            summary[key] += 1
        elif key == "idempotent":
            summary["skipped"] += 1
    return summary


def _finalize_intent(
    db: Session,
    intent: models.CaregiverNotificationIntent,
    *,
    status: str,
    reason: str,
    commit: bool,
) -> dict:
    now = _utc_now()
    intent.status = status
    intent.failure_reason = reason
    intent.processed_at = now.replace(tzinfo=None)
    if commit:
        db.commit()
        db.refresh(intent)
    return {"status": status, "reason": reason}
