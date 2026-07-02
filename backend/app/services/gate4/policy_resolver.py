"""
Gate 4D-2 — Policy resolver bridge (unwired; no DB, scheduler, or delivery).

Maps notification-like inputs to D1 ``evaluate_notification_policy()`` and returns
decisions only. No enqueue, deliver, suppress side effects, or persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from backend.app.services.gate4.notification_context import (
    map_notification_type_to_category,
    map_priority_to_risk_level,
)
from backend.app.services.gate4.notification_policy import (
    GATE4D_POLICY_VERSION,
    NotificationPolicyDecision,
    evaluate_notification_policy,
)

_FAIL_OPEN_REASON = "resolver_fail_open"


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


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
    """
    Build resolver input from notification-like fields and explicit overrides.

    Category and risk are taken from explicit args, then metadata, then legacy
    type/priority mappers. Unknown values fail open via D1 normalization.
    """
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
    """Evaluate D1 policy for a normalized resolver input."""
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
    """Resolve policy; on any error return allow with reason ``resolver_fail_open``."""
    try:
        return resolve_notification_policy_from_input(resolver_input)
    except Exception:
        return _fail_open_decision(resolver_input)


def should_enqueue(decision: NotificationPolicyDecision) -> bool:
    """True unless the policy action is suppress."""
    return decision.action != "suppress"


def should_deliver_now(decision: NotificationPolicyDecision) -> bool:
    """True only when the policy action is allow."""
    return decision.action == "allow"
