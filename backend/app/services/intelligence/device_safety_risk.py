"""I4 device safety evaluator — deterministic, no DB/network/LLM/RAG/I10.

Returns governed RiskAssessment only. Does not deliver to caregivers (B06)
or invoke B16; callers may pass EMERGENCY assessments to existing B16 seam.

Public assessment resolves rules ONLY from ACTIVE_CLINICAL_DEVICE_RULES.
Caller-supplied rule authority is forbidden.
"""

from __future__ import annotations

import inspect

from backend.app.services.intelligence.contracts import (
    LanguageCode,
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
)
from backend.app.services.intelligence.device_safety_input import (
    I4DeviceSafetyInput,
    accept_device_safety_input,
)
from backend.app.services.intelligence.device_safety_registry import (
    DEVICE_REGISTRY_VERSION,
    assert_production_registry_empty,
    select_matching_rules,
)

# Internal RiskAssessment compatibility only — does not select caregiver language
# and is not used for medical classification. B16 stores it as provenance metadata.
DEVICE_RISK_LANGUAGE: LanguageCode = "en"

NO_ACTIVE_MATCH_RULE_ID = "i4.device.rule.no_active_match.v1"
FAIL_CLOSED_RULE_ID = "i4.device.rule.fail_closed.v1"


def fail_closed_device_assessment() -> RiskAssessment:
    """Device-path fail-closed. Never NORMAL/EMERGENCY by default."""
    return RiskAssessment(
        registry_version=DEVICE_REGISTRY_VERSION,
        level=RiskLevel.NONE,
        action=SafetyAction.FAIL_CLOSED_RESPONSE,
        domain=RiskDomain.NONE,
        rule_id=FAIL_CLOSED_RULE_ID,
        language=DEVICE_RISK_LANGUAGE,
    )


def no_active_rule_assessment() -> RiskAssessment:
    """Accepted evidence with zero matching clinical rules.

    Means: no governed device safety rule matched.
    Does NOT mean healthy / normal physiology / safe patient.
    """
    return RiskAssessment(
        registry_version=DEVICE_REGISTRY_VERSION,
        level=RiskLevel.NONE,
        action=SafetyAction.CONTINUE,
        domain=RiskDomain.NONE,
        rule_id=NO_ACTIVE_MATCH_RULE_ID,
        language=DEVICE_RISK_LANGUAGE,
    )


def assess_device_safety_risk(*, input: I4DeviceSafetyInput) -> RiskAssessment:
    """Deterministic device risk assessment. Never logs health values.

    Rule authority: ACTIVE_CLINICAL_DEVICE_RULES only. No caller rule injection.
    """
    assert_production_registry_empty()
    acceptance = accept_device_safety_input(input)
    if not acceptance.ok:
        return fail_closed_device_assessment()

    matched = select_matching_rules(input)
    if not matched:
        return no_active_rule_assessment()

    # Deterministic tie-break: EMERGENCY first, then rule_id.
    priority = {
        RiskLevel.EMERGENCY: 0,
        RiskLevel.HIGH: 1,
        RiskLevel.CAUTION: 2,
        RiskLevel.NONE: 3,
    }
    winner = sorted(
        matched,
        key=lambda r: (priority.get(r.level, 99), r.rule_id),
    )[0]
    return RiskAssessment(
        registry_version=DEVICE_REGISTRY_VERSION,
        level=winner.level,
        action=winner.action,
        domain=winner.domain,
        rule_id=winner.rule_id,
        language=DEVICE_RISK_LANGUAGE,
    )


def assess_device_safety_risk_safe(*, input: I4DeviceSafetyInput) -> RiskAssessment:
    """Public seam: exceptions become FAIL_CLOSED_RESPONSE (never EMERGENCY by default)."""
    try:
        return assess_device_safety_risk(input=input)
    except Exception:
        return fail_closed_device_assessment()


def _public_assess_rejects_rules_parameter() -> bool:
    """Static guard helper for tests: public assess APIs must not accept rules=."""
    for fn in (assess_device_safety_risk, assess_device_safety_risk_safe):
        if "rules" in inspect.signature(fn).parameters:
            return False
    return True
