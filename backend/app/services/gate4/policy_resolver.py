"""
Gate 4D — Policy resolver bridge.

Maps notification-like inputs and DB prefs to D1 ``evaluate_notification_policy()``,
with optional shadow/enforce hooks for enqueue and delivery paths.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from backend.app.services.gate4.feature_flags import (
    gate4_active_conversation_defer_enabled,
    gate4_delivery_policy_enabled,
    gate4_delivery_policy_shadow_enabled,
    gate4_policy_enforce_enabled,
    gate4_policy_log_decisions_enabled,
    gate4_policy_shadow_enabled,
)
from backend.app.services.gate4.feedback_policy import augment_policy_decision_with_gate4d6
from backend.app.services.gate4.notification_context import (
    map_notification_type_to_category,
    map_priority_to_risk_level,
)
from backend.app.services.gate4.notification_contract import SmartNotificationRisk
from backend.app.services.gate4.notification_policy import (
    GATE4D_POLICY_VERSION,
    NotificationPolicyDecision,
    evaluate_notification_policy,
)
from backend.app.services.gate4.policy_prefs_bridge import (
    UserNotificationPolicyPrefs,
    load_user_notification_policy_prefs,
)

logger = logging.getLogger(__name__)

_FAIL_OPEN_REASON = "resolver_fail_open"

_REASON_CODE_ALIASES = {
    "quiet_hours": "quiet_or_sleep_deferred",
    "active_conversation": "active_conversation_deferred",
    "feedback_suppressed": "feedback_suppressed",
}


@dataclass(frozen=True)
class PolicyResolverInput:
    category: str | None = None
    channel: str | None = None
    risk_level: str | None = None
    priority: str | None = None
    quiet_hours_enabled: bool = False
    is_quiet_hours_now: bool = False
    user_channel_enabled: bool = True
    user_category_enabled: bool = True
    feedback_suppressed: bool = False
    active_conversation: bool = False
    now: datetime | None = None


@dataclass(frozen=True)
class ResolvedNotificationPolicy:
    """Runtime policy outcome with derived enqueue/delivery hints."""

    decision: NotificationPolicyDecision
    should_enqueue: bool
    should_deliver_now: bool
    reason_code: str
    is_quiet_time: bool = False
    quiet_bypass: bool = False
    local_time: Optional[str] = None
    next_allowed_at_utc: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        payload = self.decision.to_dict()
        payload.update(
            {
                "should_enqueue": self.should_enqueue,
                "should_deliver_now": self.should_deliver_now,
                "reason_code": self.reason_code,
                "is_quiet_time": self.is_quiet_time,
                "quiet_bypass": self.quiet_bypass,
                "local_time": self.local_time,
            }
        )
        if self.next_allowed_at_utc is not None:
            dt = self.next_allowed_at_utc
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            payload["next_allowed_at_utc"] = dt.astimezone(timezone.utc).isoformat()
        return payload


def map_priority_to_risk(priority: str) -> str:
    """Map legacy priority to Gate 4 risk (never map high → critical)."""
    return map_priority_to_risk_level(priority)


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _reason_code(decision: NotificationPolicyDecision) -> str:
    return _REASON_CODE_ALIASES.get(decision.reason, decision.reason)


def _resolved_from_decision(
    decision: NotificationPolicyDecision,
    *,
    is_quiet_time: bool = False,
    quiet_bypass: bool = False,
    local_time: Optional[str] = None,
) -> ResolvedNotificationPolicy:
    risk = (decision.risk_level or "").strip().lower()
    quiet_bypass = quiet_bypass or (
        risk == SmartNotificationRisk.CRITICAL.value and is_quiet_time
    )
    return ResolvedNotificationPolicy(
        decision=decision,
        should_enqueue=should_enqueue(decision),
        should_deliver_now=should_deliver_now(decision),
        reason_code=_reason_code(decision),
        is_quiet_time=is_quiet_time,
        quiet_bypass=quiet_bypass,
        local_time=local_time,
        next_allowed_at_utc=decision.defer_until,
    )


def build_resolver_input_from_notification_like(
    *,
    notification_type: str | None = None,
    priority: str | None = None,
    channel: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    quiet_hours_enabled: bool = False,
    is_quiet_hours_now: bool = False,
    user_channel_enabled: bool = True,
    user_category_enabled: bool = True,
    feedback_suppressed: bool = False,
    active_conversation: bool = False,
    now: datetime | None = None,
    category: str | None = None,
    risk_level: str | None = None,
) -> PolicyResolverInput:
    meta = metadata if isinstance(metadata, Mapping) else {}

    resolved_category = (
        _coerce_optional_str(category)
        or _coerce_optional_str(meta.get("category"))
        or map_notification_type_to_category(notification_type or "", meta)
    )
    resolved_priority = _coerce_optional_str(priority) or _coerce_optional_str(
        meta.get("priority")
    )
    resolved_risk = (
        _coerce_optional_str(risk_level)
        or _coerce_optional_str(meta.get("risk"))
        or _coerce_optional_str(meta.get("risk_level"))
    )
    if resolved_risk is None and resolved_priority is not None:
        resolved_risk = map_priority_to_risk_level(resolved_priority)

    resolved_channel = (
        _coerce_optional_str(channel)
        or _coerce_optional_str(meta.get("channel"))
        or "push"
    )

    return PolicyResolverInput(
        category=resolved_category,
        channel=resolved_channel,
        risk_level=resolved_risk,
        priority=resolved_priority,
        quiet_hours_enabled=quiet_hours_enabled,
        is_quiet_hours_now=is_quiet_hours_now,
        user_channel_enabled=user_channel_enabled,
        user_category_enabled=user_category_enabled,
        feedback_suppressed=feedback_suppressed,
        active_conversation=active_conversation,
        now=now,
    )


def resolve_notification_policy_from_input(
    resolver_input: PolicyResolverInput,
) -> NotificationPolicyDecision:
    return evaluate_notification_policy(
        category=resolver_input.category,
        channel=resolver_input.channel,
        risk_level=resolver_input.risk_level,
        priority=resolver_input.priority,
        quiet_hours_enabled=resolver_input.quiet_hours_enabled,
        is_quiet_hours_now=resolver_input.is_quiet_hours_now,
        user_channel_enabled=resolver_input.user_channel_enabled,
        user_category_enabled=resolver_input.user_category_enabled,
        feedback_suppressed=resolver_input.feedback_suppressed,
        active_conversation=resolver_input.active_conversation,
        now=resolver_input.now,
    )


def _fail_open_decision(
    resolver_input: PolicyResolverInput,
) -> NotificationPolicyDecision:
    return NotificationPolicyDecision(
        action="allow",
        reason=_FAIL_OPEN_REASON,
        risk_level=resolver_input.risk_level,
        category=resolver_input.category,
        channel=resolver_input.channel,
        policy_version=GATE4D_POLICY_VERSION,
    )


def safe_resolve_notification_policy_from_input(
    resolver_input: PolicyResolverInput,
) -> NotificationPolicyDecision:
    try:
        return resolve_notification_policy_from_input(resolver_input)
    except Exception:
        return _fail_open_decision(resolver_input)


def should_enqueue(decision: NotificationPolicyDecision) -> bool:
    return decision.action != "suppress"


def should_deliver_now(decision: NotificationPolicyDecision) -> bool:
    return decision.action == "allow"


def _prefs_to_resolver_input(
    prefs: UserNotificationPolicyPrefs,
    *,
    risk: str,
    category: str,
    channel: str,
    now_utc: datetime,
    active_conversation: bool,
) -> PolicyResolverInput:
    return PolicyResolverInput(
        category=category,
        channel=channel,
        risk_level=risk,
        quiet_hours_enabled=prefs.quiet_hours_enabled,
        is_quiet_hours_now=prefs.is_quiet_hours_now,
        user_channel_enabled=prefs.user_channel_enabled,
        user_category_enabled=prefs.user_category_enabled,
        feedback_suppressed=prefs.feedback_suppressed,
        active_conversation=active_conversation,
        now=now_utc,
    )


def resolve_notification_policy(
    db: Session,
    *,
    user_id: int,
    risk: str,
    category: str,
    channel: str = "push",
    now_utc: datetime | None = None,
    source_type: str | None = None,
    template_key: str | None = None,
    is_user_active_conversation: bool = False,
) -> ResolvedNotificationPolicy:
    """Resolve user prefs and evaluate Gate 4 policy (read-only DB)."""
    effective_now = _ensure_utc(now_utc or datetime.now(timezone.utc))
    prefs = load_user_notification_policy_prefs(
        db, user_id, now_utc=effective_now, channel=channel
    )
    active_conv = is_user_active_conversation
    if gate4_active_conversation_defer_enabled():
        from backend.app.services.gate4.feedback_policy import is_user_active_conversation

        active_conv = is_user_active_conversation(
            db, user_id=user_id, now_utc=effective_now
        )

    resolver_input = _prefs_to_resolver_input(
        prefs,
        risk=risk,
        category=category,
        channel=channel,
        now_utc=effective_now,
        active_conversation=active_conv,
    )
    decision = resolve_notification_policy_from_input(resolver_input)
    decision = augment_policy_decision_with_gate4d6(
        db,
        user_id=user_id,
        risk=risk,
        category=category,
        channel=channel,
        decision=decision,
        now_utc=effective_now,
        template_key=template_key,
    )
    risk_norm = (risk or "").strip().lower()
    quiet_bypass = (
        risk_norm == SmartNotificationRisk.CRITICAL.value
        and prefs.is_quiet_hours_now
    )
    return _resolved_from_decision(
        decision,
        is_quiet_time=prefs.is_quiet_hours_now,
        quiet_bypass=quiet_bypass,
        local_time=prefs.local_time,
    )


def apply_policy_to_enqueue_decision(
    existing_should_enqueue: bool,
    policy: ResolvedNotificationPolicy,
    *,
    enforce_enabled: bool,
    risk: str | None = None,
) -> bool:
    if not enforce_enabled:
        return existing_should_enqueue
    if not existing_should_enqueue:
        return False
    normalized_risk = (risk or "").strip().lower()
    if normalized_risk == SmartNotificationRisk.CRITICAL.value:
        return True
    return policy.should_enqueue


def _log_policy_decision(
    *,
    user_id: int,
    notification_type: str,
    risk: str,
    category: str,
    policy: ResolvedNotificationPolicy,
    enforce_enabled: bool,
    shadow_enabled: bool,
    applied: bool,
) -> None:
    if not gate4_policy_log_decisions_enabled() and not shadow_enabled:
        return
    logger.info(
        "[GATE4D4] policy_decision user_id=%s type=%s risk=%s category=%s "
        "should_enqueue=%s should_deliver_now=%s reason=%s enforce=%s shadow=%s applied=%s",
        user_id,
        notification_type,
        risk,
        category,
        policy.should_enqueue,
        policy.should_deliver_now,
        policy.reason_code,
        enforce_enabled,
        shadow_enabled,
        applied,
    )


def evaluate_enqueue_with_gate4_policy(
    db: Session,
    *,
    user_id: int,
    existing_should_enqueue: bool,
    notification_type: str,
    priority: str,
    channel: str | None = None,
    now_utc: datetime | None = None,
    metadata: Optional[dict[str, Any]] = None,
    source_type: str | None = None,
    template_key: str | None = None,
) -> tuple[bool, Optional[ResolvedNotificationPolicy]]:
    """Evaluate Gate 4 policy for enqueue. Fail-open on resolver error."""
    meta = metadata or {}
    risk = str(meta.get("risk") or map_priority_to_risk(priority)).strip().lower()
    category = str(
        meta.get("category") or map_notification_type_to_category(notification_type, meta)
    ).strip().lower()
    effective_channel = channel or str(meta.get("channel") or "push")

    shadow_enabled = gate4_policy_shadow_enabled()
    enforce_enabled = gate4_policy_enforce_enabled()

    if not shadow_enabled and not enforce_enabled:
        return existing_should_enqueue, None

    try:
        policy = resolve_notification_policy(
            db,
            user_id=user_id,
            risk=risk,
            category=category,
            channel=effective_channel,
            now_utc=now_utc,
            source_type=source_type or meta.get("source_type"),
            template_key=template_key or meta.get("template_key"),
            is_user_active_conversation=False,
        )
    except Exception:
        logger.exception(
            "[GATE4D4] policy_resolver_failed user_id=%s type=%s risk=%s (fail-open)",
            user_id,
            notification_type,
            risk,
        )
        return existing_should_enqueue, None

    should_enqueue_result = apply_policy_to_enqueue_decision(
        existing_should_enqueue,
        policy,
        enforce_enabled=enforce_enabled,
        risk=risk,
    )

    _log_policy_decision(
        user_id=user_id,
        notification_type=notification_type,
        risk=risk,
        category=category,
        policy=policy,
        enforce_enabled=enforce_enabled,
        shadow_enabled=shadow_enabled,
        applied=should_enqueue_result != existing_should_enqueue,
    )

    return should_enqueue_result, policy


def apply_policy_to_delivery_decision(
    policy: ResolvedNotificationPolicy,
    *,
    enforce_enabled: bool,
    risk: str,
) -> bool:
    if not enforce_enabled:
        return True
    normalized_risk = (risk or "").strip().lower()
    if normalized_risk == SmartNotificationRisk.CRITICAL.value:
        return True
    if normalized_risk == SmartNotificationRisk.DO_NOT_NOTIFY.value:
        return False
    return policy.should_deliver_now


def _notification_risk_and_category(notification: Any) -> tuple[str, str]:
    meta_risk = None
    if getattr(notification, "risk_level", None):
        meta_risk = notification.risk_level
    risk = map_priority_to_risk(getattr(notification, "priority", None) or "normal")
    if meta_risk:
        risk = str(meta_risk).strip().lower()
    category = map_notification_type_to_category(
        getattr(notification, "type", None) or "",
        {"category": getattr(notification, "category", None)},
    )
    if getattr(notification, "category", None):
        category = str(notification.category).strip().lower()
    return risk, category


def evaluate_delivery_with_gate4_policy(
    db: Session,
    *,
    notification: Any,
    now_utc: datetime | None = None,
) -> tuple[bool, Optional[ResolvedNotificationPolicy]]:
    """Evaluate Gate 4 policy for delivery. Fail-open on resolver error."""
    delivery_enforce = gate4_delivery_policy_enabled()
    delivery_shadow = gate4_delivery_policy_shadow_enabled()

    if not delivery_enforce and not delivery_shadow:
        return True, None

    user_id = int(notification.user_id)
    notification_type = str(getattr(notification, "type", None) or "")
    risk, category = _notification_risk_and_category(notification)
    effective_channel = str(getattr(notification, "channel", None) or "push")
    effective_now = _ensure_utc(now_utc or datetime.now(timezone.utc))

    try:
        policy = resolve_notification_policy(
            db,
            user_id=user_id,
            risk=risk,
            category=category,
            channel=effective_channel,
            now_utc=effective_now,
            template_key=getattr(notification, "template_key", None),
            is_user_active_conversation=False,
        )
    except Exception:
        logger.exception(
            "[GATE4D4B] delivery_policy_resolver_failed notification_id=%s user_id=%s (fail-open)",
            getattr(notification, "id", None),
            user_id,
        )
        return True, None

    should_deliver = apply_policy_to_delivery_decision(
        policy,
        enforce_enabled=delivery_enforce,
        risk=risk,
    )

    if gate4_policy_log_decisions_enabled() or delivery_shadow:
        logger.info(
            "[GATE4D4B] delivery_policy notification_id=%s user_id=%s type=%s risk=%s "
            "category=%s should_deliver_now=%s reason=%s enforce=%s shadow=%s should_deliver=%s",
            getattr(notification, "id", None),
            user_id,
            notification_type,
            risk,
            category,
            policy.should_deliver_now,
            policy.reason_code,
            delivery_enforce,
            delivery_shadow,
            should_deliver if delivery_enforce else True,
        )

    if not delivery_enforce:
        return True, policy

    return should_deliver, policy


def defer_notification_delivery(
    notification: Any,
    policy: Optional[ResolvedNotificationPolicy],
) -> Optional[datetime]:
    """Apply in-memory defer fields for skipped delivery (no DB commit)."""
    if policy and policy.next_allowed_at_utc is not None:
        next_at = _ensure_utc(policy.next_allowed_at_utc).replace(tzinfo=None)
        notification.scheduled_for = next_at
        return next_at
    if policy and policy.decision.defer_until is not None:
        next_at = _ensure_utc(policy.decision.defer_until).replace(tzinfo=None)
        notification.scheduled_for = next_at
        return next_at
    return None
