"""Gate 5-G — ML inference → V1 care suggestion bridge (default OFF)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.models import DeviceEvent, InteractionEvent, MlInferenceRecord, Notification
from backend.app.services.gate4.notification_context import (
    NotificationCategory,
    NotificationRiskLevel,
    NotificationSourceType,
)
from backend.app.services.gate5.ml_flags import (
    ml_care_bridge_enabled,
    ml_chat_context_enabled,
    ml_log_decisions,
    ml_notification_enabled,
)
from backend.app.services.gate5.ml_safety import build_v1_care_suggestion_text, validate_user_facing_text

logger = logging.getLogger(__name__)

BRIDGEABLE_OUTPUT_TYPES = frozenset(
    {
        "possible_anomaly",
        "unusual_pattern",
        "signal_quality_issue",
        "care_suggestion_candidate",
        "low_confidence",
    }
)


class MlCareBridgeError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class CareBridgeResult:
    record_id: int
    output_type: str
    care_suggestion_text: str
    dry_run: bool
    bridge_enabled: bool
    notification_enabled: bool
    chat_context_enabled: bool
    device_event_id: Optional[int]
    notification_id: Optional[int]
    interaction_event_id: Optional[int]
    blocked_reason: Optional[str]


def _map_device_event_type(output_type: str) -> str:
    if output_type == "signal_quality_issue":
        return "signal_quality_issue"
    if output_type in ("possible_anomaly", "unusual_pattern"):
        return "possible_anomaly_shadow"
    return "care_suggestion_candidate"


def run_care_bridge(
    db: Session,
    record_id: int,
    *,
    dry_run: bool = True,
    care_text_override: Optional[str] = None,
) -> CareBridgeResult:
    """
    Bridge ML inference to V1 care suggestion candidate.

    dry_run=True: preview only — no DB side effects.
    dry_run=False: requires SEDI_GATE5_ML_CARE_BRIDGE_ENABLED; notifications/chat require extra flags.
    """
    row = db.query(MlInferenceRecord).filter(MlInferenceRecord.id == record_id).first()
    if not row:
        raise MlCareBridgeError("RECORD_NOT_FOUND", f"inference record {record_id} not found", 404)

    if row.output_type not in BRIDGEABLE_OUTPUT_TYPES:
        raise MlCareBridgeError(
            "OUTPUT_NOT_BRIDGEABLE",
            f"output_type '{row.output_type}' is not eligible for care bridge",
            422,
        )

    if row.user_visible:
        raise MlCareBridgeError("USER_VISIBLE_FORBIDDEN", "record must remain internal/shadow", 422)

    care_text = care_text_override or build_v1_care_suggestion_text(row.output_type)
    try:
        care_text = validate_user_facing_text(care_text)
    except Exception as exc:
        raise MlCareBridgeError("UNSAFE_CARE_TEXT", str(exc), 422) from exc

    bridge_on = ml_care_bridge_enabled()
    notif_on = ml_notification_enabled()
    chat_on = ml_chat_context_enabled()

    if ml_log_decisions():
        logger.info(
            "[ML_CARE_BRIDGE] record_id=%s dry_run=%s bridge=%s notif=%s chat=%s output_type=%s",
            record_id,
            dry_run,
            bridge_on,
            notif_on,
            chat_on,
            row.output_type,
        )

    if dry_run:
        return CareBridgeResult(
            record_id=record_id,
            output_type=row.output_type,
            care_suggestion_text=care_text,
            dry_run=True,
            bridge_enabled=bridge_on,
            notification_enabled=notif_on,
            chat_context_enabled=chat_on,
            device_event_id=None,
            notification_id=None,
            interaction_event_id=None,
            blocked_reason=None,
        )

    if not bridge_on:
        return CareBridgeResult(
            record_id=record_id,
            output_type=row.output_type,
            care_suggestion_text=care_text,
            dry_run=False,
            bridge_enabled=False,
            notification_enabled=notif_on,
            chat_context_enabled=chat_on,
            device_event_id=None,
            notification_id=None,
            interaction_event_id=None,
            blocked_reason="SEDI_GATE5_ML_CARE_BRIDGE_ENABLED is OFF",
        )

    device_event_id: Optional[int] = None
    notification_id: Optional[int] = None
    interaction_event_id: Optional[int] = None

    event_type = _map_device_event_type(row.output_type)
    payload = {
        "inference_record_id": row.id,
        "output_type": row.output_type,
        "score": row.score,
        "confidence": row.confidence,
        "care_suggestion_preview": care_text,
        "bridge_version": "gate5g_v1",
        "user_visible": False,
    }
    device_event = DeviceEvent(
        user_id=row.user_id,
        device_id=row.device_id,
        event_type=event_type,
        payload_json=json.dumps(payload, ensure_ascii=False),
        recorded_at=datetime.utcnow(),
        dedupe_key=f"ml_bridge:{row.id}:{event_type}",
    )
    db.add(device_event)
    db.flush()
    device_event_id = device_event.id

    if notif_on:
        from backend.app.schemas.notification import NotificationPayload
        from backend.app.services.i10.contracts import I10NotificationCandidate
        from backend.app.services.i10.intake import enqueue_i10_notification
        from backend.app.services.i10.policy_types import (
            I10DecisionValue,
            I10NotificationScope,
            I10PrivacyClass,
            I10SemanticFamily,
        )
        from backend.app.services.i10.self_producer_adapter import (
            resolve_or_ensure_self_health_subject_id,
        )

        health_subject_id = resolve_or_ensure_self_health_subject_id(db, int(row.user_id))
        dedupe_key = f"ml_care:{row.id}"
        # Contract type connection_ping; restore care_suggestion presentation after I10 SEND.
        payload = NotificationPayload(
            user_id=int(row.user_id),
            type="connection_ping",
            title="Sedi care signal",
            body=care_text,
            priority="normal",
            scheduled_for=None,
            dedupe_key=dedupe_key,
            metadata={
                "legacy_producer": "ml_care_bridge",
                "ml_output_type": row.output_type,
                "ml_type": "care_suggestion",
            },
            category=NotificationCategory.CARE_FOLLOW_UP.value,
            source_type=NotificationSourceType.DEVICE_EVENT.value,
            source_id=str(device_event_id),
            risk_level=NotificationRiskLevel.INFORMATIONAL.value,
            template_key="gate5_ml_care_suggestion",
            context={
                "template_key": "gate5_ml_care_suggestion",
                "trigger_reason": row.output_type,
                "source_summary_key": "ml_inference_shadow",
            },
        )
        candidate = I10NotificationCandidate(
            candidate_key=dedupe_key,
            health_subject_id=health_subject_id,
            recipient_user_id=int(row.user_id),
            notification_scope=I10NotificationScope.CARE_ACTION,
            source_owner="ML_CARE_BRIDGE_ADAPTER",
            source_type="ml_care_bridge",
            source_id=str(row.id),
            semantic_family=I10SemanticFamily.CARE_ACTION,
            privacy_hint=I10PrivacyClass.HEALTH_SENSITIVE,
        )
        intake = enqueue_i10_notification(db, candidate=candidate, payload=payload, check_dedupe=True)
        if intake.decision == I10DecisionValue.SEND and intake.notification_id is not None:
            notification = (
                db.query(Notification)
                .filter(Notification.id == intake.notification_id)
                .one()
            )
            notification.type = "care_suggestion"
            notification.template_key = "gate5_ml_care_suggestion"
            notification.source_type = NotificationSourceType.DEVICE_EVENT.value
            notification.source_id = str(device_event_id)
            notification.category = NotificationCategory.CARE_FOLLOW_UP.value
            notification.risk_level = NotificationRiskLevel.INFORMATIONAL.value
            db.add(notification)
            db.flush()
            notification_id = notification.id
        else:
            logger.info(
                "[ML_CARE_BRIDGE] I10 suppressed notification record_id=%s decision=%s reason=%s",
                record_id,
                intake.decision.value,
                intake.reason_code,
            )

    if chat_on:
        chat_meta = {
            "inference_record_id": row.id,
            "device_event_id": device_event_id,
            "output_type": row.output_type,
            "care_suggestion_text": care_text,
            "ml_bridge": True,
        }
        interaction = InteractionEvent(
            user_id=row.user_id,
            event_type="ml_care_context",
            source="ml_bridge",
            interaction_channel="text",
            source_type=NotificationSourceType.DEVICE_EVENT.value,
            source_id=str(device_event_id),
            metadata_json=json.dumps(chat_meta, ensure_ascii=False),
        )
        db.add(interaction)
        db.flush()
        interaction_event_id = interaction.id

    db.commit()

    return CareBridgeResult(
        record_id=record_id,
        output_type=row.output_type,
        care_suggestion_text=care_text,
        dry_run=False,
        bridge_enabled=True,
        notification_enabled=notif_on,
        chat_context_enabled=chat_on,
        device_event_id=device_event_id,
        notification_id=notification_id,
        interaction_event_id=interaction_event_id,
        blocked_reason=None,
    )
