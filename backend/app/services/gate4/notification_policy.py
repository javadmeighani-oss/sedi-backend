"""
Gate 4D-1 — Pure notification policy (no DB, scheduler, delivery, or router wiring).

Evaluates allow / defer / suppress for a single notification candidate from
pre-resolved inputs. Runtime integration is a later gate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from backend.app.services.gate4.notification_contract import SmartNotificationRisk

GATE4D_POLICY_VERSION = "4d.1"

PolicyAction = Literal["allow", "defer", "suppress"]

_PRIORITY_TO_RISK: dict[str, str] = {
    "critical": SmartNotificationRisk.CRITICAL.value,
    "high": SmartNotificationRisk.HIGH.value,
    "normal": SmartNotificationRisk.NORMAL.value,
    "low": SmartNotificationRisk.LOW.value,
    "informational": SmartNotificationRisk.INFORMATIONAL.value,
    "do_not_notify": SmartNotificationRisk.DO_NOT_NOTIFY.value,
}

_ACTIVE_CONVERSATION_DEFER_MINUTES = 15


@dataclass(frozen=True)
class NotificationPolicyDecision:
    """Serializable policy outcome for one notification evaluation."""

    action: PolicyAction
    reason: str
    risk_level: Optional[str] = None
    category: Optional[str] = None
    channel: Optional[str] = None
    defer_until: Optional[datetime] = None
    policy_version: str = GATE4D_POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Stable JSON-friendly representation (no PII)."""
        payload = asdict(self)
        if self.defer_until is not None:
            dt = self.defer_until
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            payload["defer_until"] = dt.astimezone(timezone.utc).isoformat()
        return payload


def _normalize_risk(
    risk_level: Optional[str],
    priority: Optional[str],
) -> str:
    """Resolve effective risk; unknown values fail open to normal."""
    if risk_level is not None:
        candidate = str(risk_level).strip().lower()
        if candidate:
            return candidate
    if priority is not None:
        key = str(priority).strip().lower()
        if key in _PRIORITY_TO_RISK:
            return _PRIORITY_TO_RISK[key]
    return SmartNotificationRisk.NORMAL.value


def _is_critical_risk(risk: str) -> bool:
    return risk == SmartNotificationRisk.CRITICAL.value


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _base_decision(
    *,
    action: PolicyAction,
    reason: str,
    risk_level: Optional[str],
    category: Optional[str],
    channel: Optional[str],
    defer_until: Optional[datetime] = None,
) -> NotificationPolicyDecision:
    return NotificationPolicyDecision(
        action=action,
        reason=reason,
        risk_level=risk_level,
        category=category,
        channel=channel,
        defer_until=defer_until,
    )


def evaluate_notification_policy(
    *,
    category: Optional[str] = None,
    channel: Optional[str] = None,
    risk_level: Optional[str] = None,
    priority: Optional[str] = None,
    quiet_hours_enabled: bool = False,
    is_quiet_hours_now: bool = False,
    user_channel_enabled: bool = True,
    user_category_enabled: bool = True,
    feedback_suppressed: bool = False,
    active_conversation: bool = False,
    now: Optional[datetime] = None,
) -> NotificationPolicyDecision:
    """
    Pure policy evaluation for one notification candidate.

    Precedence (non-critical):
    1. User-disabled channel/category → suppress
    2. Feedback suppression → suppress
    3. Quiet hours → defer
    4. Active conversation → defer
    5. Default → allow

    Critical risk bypasses feedback, quiet hours, and active-conversation deferral.
    Critical is still delivered when user prefs are disabled (safety).
    """
    effective_risk = _normalize_risk(risk_level, priority)
    effective_now = _ensure_utc(now or datetime.now(timezone.utc))
    cat = (category or "").strip().lower() or None
    ch = (channel or "").strip().lower() or None

    if effective_risk == SmartNotificationRisk.DO_NOT_NOTIFY.value:
        return _base_decision(
            action="suppress",
            reason="do_not_notify",
            risk_level=effective_risk,
            category=cat,
            channel=ch,
        )

    if _is_critical_risk(effective_risk):
        return _base_decision(
            action="allow",
            reason="critical_allowed",
            risk_level=effective_risk,
            category=cat,
            channel=ch,
        )

    if not user_channel_enabled or not user_category_enabled:
        return _base_decision(
            action="suppress",
            reason="user_preference_disabled",
            risk_level=effective_risk,
            category=cat,
            channel=ch,
        )

    if feedback_suppressed:
        return _base_decision(
            action="suppress",
            reason="feedback_suppressed",
            risk_level=effective_risk,
            category=cat,
            channel=ch,
        )

    if quiet_hours_enabled and is_quiet_hours_now:
        return _base_decision(
            action="defer",
            reason="quiet_hours",
            risk_level=effective_risk,
            category=cat,
            channel=ch,
            defer_until=effective_now + timedelta(hours=8),
        )

    if active_conversation:
        return _base_decision(
            action="defer",
            reason="active_conversation",
            risk_level=effective_risk,
            category=cat,
            channel=ch,
            defer_until=effective_now + timedelta(minutes=_ACTIVE_CONVERSATION_DEFER_MINUTES),
        )

    return _base_decision(
        action="allow",
        reason="allowed",
        risk_level=effective_risk,
        category=cat,
        channel=ch,
    )
