"""
Gate 4-B — Notification traceability context (category, source, risk, safe context_json).

Pure helpers + constants. No FCM, scheduler, or GPT I/O.
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from typing import Any, Final, Mapping, Optional

logger = logging.getLogger(__name__)

GATE4B_CONTEXT_VERSION: Final[str] = "4b.2"


class NotificationCategory(str, Enum):
    DAILY_STATUS = "daily_status"
    REMINDER = "reminder"
    EVENT_REMINDER = "event_reminder"
    MEDICATION_REMINDER = "medication_reminder"
    CARE_FOLLOW_UP = "care_follow_up"
    CARE_RECOMMENDATION = "care_recommendation"
    ENGAGEMENT_CHECKIN = "engagement_checkin"
    HEALTH_STATUS = "health_status"
    DEVICE_ALERT = "device_alert"
    CRITICAL_ALERT = "critical_alert"
    CHAT_CONTINUATION = "chat_continuation"
    SYSTEM = "system"


class NotificationSourceType(str, Enum):
    CONVERSATION = "conversation"
    INTERACTION_EVENT = "interaction_event"
    USER_EVENT = "user_event"
    MEDICATION_SCHEDULE = "medication_schedule"
    CARE_FOLLOW_UP_TASK = "care_follow_up_task"
    CARE_RECOMMENDATION = "care_recommendation"
    CARE_RISK_ASSESSMENT = "care_risk_assessment"
    HEALTH_QUESTION = "health_question"
    SYMPTOM_REPORT = "symptom_report"
    USER_GOAL = "user_goal"
    USER_RESTRICTION = "user_restriction"
    DAILY_ROUTINE = "daily_routine"
    KNOWLEDGE_DOCUMENT = "knowledge_document"
    KNOWLEDGE_CHUNK = "knowledge_chunk"
    DEVICE_EVENT = "device_event"
    SYSTEM_SCHEDULER = "system_scheduler"


class NotificationRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    DO_NOT_NOTIFY = "do_not_notify"
    # Align with existing Gate 4 policy contract
    NORMAL = "normal"
    INFORMATIONAL = "informational"


ALLOWED_CONTEXT_JSON_KEYS: Final[frozenset[str]] = frozenset(
    {
        "template_key",
        "trigger_reason",
        "schedule_label",
        "schedule_time",
        "job_id",
        "rule_id",
        "action_hint",
        "source_summary_key",
        "dedupe_hint",
        "recurrence_hint",
    }
)

_FORBIDDEN_CONTEXT_KEY_SUBSTRINGS: Final[tuple[str, ...]] = (
    "phone",
    "address",
    "caregiver",
    "token",
    "api_key",
    "password",
    "secret",
    "payload",
    "diagnosis",
    "dosage",
    "medication_change",
    "raw_message",
    "user_message",
    "chunk",
    "kb_content",
)


def map_notification_type_to_category(
    notification_type: str,
    metadata: Optional[Mapping[str, Any]] = None,
) -> str:
    """Map legacy Notification.type (+ optional metadata) to persisted Gate 4-B category."""
    key = (notification_type or "").strip().lower()
    meta = metadata or {}

    if key == "morning_brief":
        return NotificationCategory.DAILY_STATUS.value

    if key in ("connection_ping", "companion_ping", "engagement_nudge"):
        return NotificationCategory.ENGAGEMENT_CHECKIN.value

    if key == "device_disconnected":
        return NotificationCategory.DEVICE_ALERT.value

    if key == "health_alert":
        alert_code = str(meta.get("alert_code") or "").strip().lower()
        if alert_code == "medication_reminder":
            return NotificationCategory.MEDICATION_REMINDER.value
        if meta.get("priority") == "critical" or meta.get("risk_level") == NotificationRiskLevel.CRITICAL.value:
            return NotificationCategory.CRITICAL_ALERT.value
        return NotificationCategory.HEALTH_STATUS.value

    return NotificationCategory.SYSTEM.value


def map_priority_to_risk_level(priority: str) -> str:
    """Map legacy Notification.priority to persisted Gate 4-B risk_level."""
    key = (priority or "normal").strip().lower()
    mapping = {
        "critical": NotificationRiskLevel.CRITICAL.value,
        "high": NotificationRiskLevel.HIGH.value,
        "low": NotificationRiskLevel.LOW.value,
        "normal": NotificationRiskLevel.NORMAL.value,
        "informational": NotificationRiskLevel.INFORMATIONAL.value,
        "do_not_notify": NotificationRiskLevel.DO_NOT_NOTIFY.value,
        "medium": NotificationRiskLevel.MEDIUM.value,
    }
    return mapping.get(key, NotificationRiskLevel.NORMAL.value)


def _is_forbidden_context_key(key: str) -> bool:
    lowered = (key or "").strip().lower()
    if not lowered:
        return True
    if lowered not in ALLOWED_CONTEXT_JSON_KEYS:
        return True
    return any(fragment in lowered for fragment in _FORBIDDEN_CONTEXT_KEY_SUBSTRINGS)


def sanitize_notification_context(context: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """
    Return a small allowlisted context dict safe for context_json storage.
    Disallowed keys are dropped silently; drops are logged without values.
    """
    if not context:
        return None
    if not isinstance(context, dict):
        return None

    cleaned: dict[str, Any] = {}
    for raw_key, raw_value in context.items():
        key = str(raw_key).strip()
        if _is_forbidden_context_key(key):
            if key and key not in ALLOWED_CONTEXT_JSON_KEYS:
                logger.warning("[GATE4B] dropped disallowed context_json key=%s", key)
            continue
        if raw_value is None:
            continue
        if isinstance(raw_value, (str, int, float, bool)):
            cleaned[key] = raw_value if not isinstance(raw_value, str) else raw_value[:256]
        else:
            logger.warning("[GATE4B] dropped non-scalar context_json key=%s", key)
    return cleaned or None


def serialize_notification_context(context: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Sanitize and JSON-serialize context for DB storage."""
    cleaned = sanitize_notification_context(context)
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))


def build_scheduler_context(
    *,
    job_id: str,
    rule_id: Optional[str] = None,
    template_key: Optional[str] = None,
    trigger_reason: Optional[str] = None,
) -> dict[str, Any]:
    """Safe context_json payload for scheduler-driven notifications."""
    ctx: dict[str, Any] = {"job_id": job_id[:64]}
    if rule_id:
        ctx["rule_id"] = rule_id[:100]
    if template_key:
        ctx["template_key"] = template_key[:100]
    if trigger_reason:
        ctx["trigger_reason"] = trigger_reason[:128]
    return sanitize_notification_context(ctx) or {}


def resolve_effective_category(
    *,
    category: Optional[str],
    notification_type: str,
    metadata: Optional[Mapping[str, Any]] = None,
    context_json: Optional[str] = None,
) -> str:
    """Runtime fallback when persisted category is null (legacy rows)."""
    if category:
        return category
    merged_meta = dict(metadata or {})
    if context_json:
        try:
            parsed = json.loads(context_json)
            if isinstance(parsed, dict):
                merged_meta.update(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    return map_notification_type_to_category(notification_type, merged_meta)


def resolve_effective_risk_level(
    *,
    risk_level: Optional[str],
    priority: str,
) -> str:
    if risk_level:
        return risk_level
    return map_priority_to_risk_level(priority)


def resolve_traceability_fields(
    *,
    notification_type: str,
    priority: str,
    category: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    context: Optional[Mapping[str, Any]] = None,
    risk_level: Optional[str] = None,
    template_key: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """
    Resolve all Gate 4-B traceability fields for Notification ORM persistence.
    """
    meta = metadata or {}
    resolved_category = category or map_notification_type_to_category(notification_type, meta)
    resolved_risk = risk_level or map_priority_to_risk_level(priority)
    resolved_template = template_key or meta.get("template_key")
    if isinstance(resolved_template, str):
        resolved_template = resolved_template[:100] or None
    else:
        resolved_template = None

    resolved_source_type = source_type or meta.get("source_type")
    resolved_source_id = source_id or meta.get("source_id")
    if resolved_source_id is not None:
        resolved_source_id = str(resolved_source_id)[:255]

    ctx = dict(context or {})
    if resolved_template and "template_key" not in ctx:
        ctx["template_key"] = resolved_template
    if meta.get("schedule_time") and "schedule_time" not in ctx:
        ctx["schedule_time"] = str(meta["schedule_time"])[:32]

    return {
        "category": resolved_category,
        "source_type": str(resolved_source_type)[:64] if resolved_source_type else None,
        "source_id": resolved_source_id,
        "context_json": serialize_notification_context(ctx),
        "risk_level": resolved_risk,
        "template_key": resolved_template,
    }
