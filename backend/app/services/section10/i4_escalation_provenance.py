"""Bounded I4 → Section10 escalation provenance (metadata_json only; no raw chat)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from backend.app import models
from backend.app.services.intelligence.contracts import (
    RiskAssessment,
    RiskLevel,
    SafetyAction,
)

AUTHORITY_SOURCE = "SECTION15_I4"
AUTHORITY_VERSION = "I4_ESCALATION_PROVENANCE_V1"
READY_STATE = "caregiver_escalation_ready"

_REQUIRED_STRING_FIELDS = (
    "authority_source",
    "authority_version",
    "registry_version",
    "rule_id",
    "risk_level",
    "safety_action",
    "risk_domain",
    "language",
    "occurred_at",
    "occurrence_id",
)


def new_occurrence_id() -> str:
    return str(uuid4())


def utc_occurred_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_authoritative_i4_emergency_assessment(assessment: object) -> bool:
    return (
        isinstance(assessment, RiskAssessment)
        and assessment.level is RiskLevel.EMERGENCY
        and assessment.action is SafetyAction.RETURN_EMERGENCY_RESPONSE
    )


def parse_escalation_metadata(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def build_i4_escalation_provenance(
    *,
    risk_assessment: RiskAssessment,
    health_subject_id: int,
    occurrence_id: str,
    policy: Optional[dict[str, Any]] = None,
    occurred_at: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "authority_source": AUTHORITY_SOURCE,
        "authority_version": AUTHORITY_VERSION,
        "registry_version": risk_assessment.registry_version,
        "rule_id": risk_assessment.rule_id,
        "risk_level": risk_assessment.level.value,
        "safety_action": risk_assessment.action.value,
        "risk_domain": risk_assessment.domain.value,
        "language": risk_assessment.language,
        "occurred_at": occurred_at or utc_occurred_at(),
        "health_subject_id": int(health_subject_id),
        "occurrence_id": occurrence_id,
    }
    if policy is not None:
        payload["policy"] = policy
    return payload


def is_valid_i4_escalation_provenance(meta: object) -> bool:
    if not isinstance(meta, dict):
        return False
    if meta.get("authority_source") != AUTHORITY_SOURCE:
        return False
    if meta.get("authority_version") != AUTHORITY_VERSION:
        return False
    if meta.get("risk_level") != RiskLevel.EMERGENCY.value:
        return False
    if meta.get("safety_action") != SafetyAction.RETURN_EMERGENCY_RESPONSE.value:
        return False
    for key in _REQUIRED_STRING_FIELDS:
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    try:
        hs_id = int(meta.get("health_subject_id"))
    except (TypeError, ValueError):
        return False
    return hs_id > 0


def record_has_valid_i4_provenance(record: models.EmergencyEscalationRecord) -> bool:
    return is_valid_i4_escalation_provenance(parse_escalation_metadata(record.metadata_json))
