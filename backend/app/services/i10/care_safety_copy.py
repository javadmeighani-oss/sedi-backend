"""I10-B16 CARE_SAFETY copy and metadata — bounded I4 escalation outcome only."""

from __future__ import annotations

from backend.app import models
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily

PRODUCER_OWNER = "I10_CARE_SAFETY"


def build_care_safety_occurrence_key(
    *,
    health_subject_id: int,
    escalation_id: int,
) -> str:
    return f"i10:care:care_safety:{health_subject_id}:{escalation_id}"


def render_care_safety_body(
    record: models.EmergencyEscalationRecord,
    *,
    include_bounded_detail: bool = False,
) -> str:
    base = (
        "A governed safety escalation for your care recipient needs attention. "
        "This notice does not confirm that safety has been resolved."
    )
    if include_bounded_detail and record.reason_category:
        reason = str(record.reason_category).strip()[:64]
        return f"{base} Escalation reason: {reason}."
    return base


def build_care_safety_metadata(
    record: models.EmergencyEscalationRecord,
    *,
    health_subject_id: int,
    body: str,
    include_bounded_detail: bool = False,
) -> dict:
    context: dict = {
        "template_key": "care_safety_escalation",
        "trigger_reason": "i4_escalation_occurrence",
        "escalation_state": record.current_state,
        "source_summary_key": f"emergency_escalation:{record.id}",
    }
    payload: dict = {
        "title": "Safety escalation",
        "body": body,
        "template_key": "care_safety_escalation",
        "trigger_reason": "i4_escalation_occurrence",
        "escalation_id": int(record.id),
        "context": context,
        "semantic_family": I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        "privacy_class": I10PrivacyClass.HEALTH_SENSITIVE.value,
        "source_entity_type": PRODUCER_OWNER,
        "source_entity_id": str(record.id),
        "health_subject_id": health_subject_id,
        "bounded_detail_included": include_bounded_detail,
    }
    if include_bounded_detail and record.reason_category:
        bounded_reason = str(record.reason_category).strip()[:64]
        context["reason_category"] = bounded_reason
        payload["reason_category"] = bounded_reason
    return payload
