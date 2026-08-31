"""I10 persisted vocabulary — documentation/constants for CheckConstraint alignment."""

from __future__ import annotations

from enum import Enum


class I10SemanticFamily(str, Enum):
    GENERAL_STATUS = "GENERAL_STATUS"
    DEVICE_STATUS = "DEVICE_STATUS"
    CARE_ACTION = "CARE_ACTION"
    SAFETY_ESCALATION = "SAFETY_ESCALATION"
    ENGAGEMENT = "ENGAGEMENT"
    REMINDER = "REMINDER"
    SYSTEM = "SYSTEM"
    MORNING_CHECK_IN = "MORNING_CHECK_IN"
    PRESENCE_REENGAGEMENT = "PRESENCE_REENGAGEMENT"
    ENGAGEMENT_NUDGE = "ENGAGEMENT_NUDGE"


class I10NotificationScope(str, Enum):
    GENERAL_STATUS = "GENERAL_STATUS"
    DEVICE_STATUS = "DEVICE_STATUS"
    CARE_ACTION = "CARE_ACTION"
    SAFETY_ESCALATION = "SAFETY_ESCALATION"
    SENSITIVE_HEALTH_DETAIL = "SENSITIVE_HEALTH_DETAIL"


class I10RecipientKind(str, Enum):
    SELF = "SELF"
    CAREGIVER = "CAREGIVER"
    MANAGER = "MANAGER"


class I10PrivacyClass(str, Enum):
    PUBLIC_SAFE = "PUBLIC_SAFE"
    PRIVATE = "PRIVATE"
    HEALTH_SENSITIVE = "HEALTH_SENSITIVE"


class I10PreviewMode(str, Enum):
    """Push/inbox preview tier — rendering deferred to later gates."""

    FULL_PREVIEW = "FULL_PREVIEW"
    PRIVACY_SAFE_PREVIEW = "PRIVACY_SAFE_PREVIEW"
    HIDDEN_CONTENT = "HIDDEN_CONTENT"


class I10DecisionValue(str, Enum):
    SEND = "SEND"
    DEFER = "DEFER"
    SUPPRESS = "SUPPRESS"
    BUNDLE = "BUNDLE"
    ESCALATE = "ESCALATE"
    EXPIRE = "EXPIRE"


PRIVACY_TO_PREVIEW_DEFAULT: dict[I10PrivacyClass, I10PreviewMode] = {
    I10PrivacyClass.PUBLIC_SAFE: I10PreviewMode.FULL_PREVIEW,
    I10PrivacyClass.PRIVATE: I10PreviewMode.PRIVACY_SAFE_PREVIEW,
    I10PrivacyClass.HEALTH_SENSITIVE: I10PreviewMode.HIDDEN_CONTENT,
}
