"""I10-B15 CARE_ACTION copy and metadata — no clinical instruction invention."""

from __future__ import annotations

from backend.app import models
from backend.app.services.i10.policy_types import I10PrivacyClass, I10SemanticFamily

PRODUCER_OWNER = "I10_CARE_ACTION"


def build_care_action_occurrence_key(
    *,
    health_subject_id: int,
    action_id: int,
    valid_from_iso: str,
) -> str:
    return f"i10:care:care_action:{health_subject_id}:{action_id}:{valid_from_iso}"


def render_care_action_body(action: models.I8OperationalPlanAction) -> str:
    summary = (action.summary_text or "a governed care action").strip()[:200]
    return (
        f"A governed care action registered for your care recipient is due: "
        f"'{summary}'. This notice does not confirm completion."
    )


def build_care_action_metadata(
    action: models.I8OperationalPlanAction,
    *,
    health_subject_id: int,
    body: str,
) -> dict:
    valid_from_iso = action.valid_from.isoformat() if action.valid_from else str(action.id)
    return {
        "title": "Care action due",
        "body": body,
        "template_key": "care_action",
        "trigger_reason": "managed_i8_care_action",
        "action_domain": action.action_domain,
        "i8_action_id": int(action.id),
        "context": {
            "template_key": "care_action",
            "trigger_reason": "managed_i8_care_action",
            "action_domain": action.action_domain,
            "source_summary_key": f"i8_action:{action.id}",
        },
        "semantic_family": I10SemanticFamily.CARE_ACTION.value,
        "privacy_class": I10PrivacyClass.HEALTH_SENSITIVE.value,
        "source_entity_type": PRODUCER_OWNER,
        "source_entity_id": str(action.id),
        "occurrence_valid_from": valid_from_iso,
        "health_subject_id": health_subject_id,
    }
