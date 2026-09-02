"""I10-B18 canonical interruption policy — Gate4 reuse + B14 overlap + B05/B06 boundary."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from backend.app.services.gate4.notification_contract import SmartNotificationRisk
from backend.app.services.gate4.notification_context import map_notification_type_to_category
from backend.app.services.gate4.notification_policy import GATE4D_POLICY_VERSION
from backend.app.services.gate4.policy_resolver import resolve_notification_policy
from backend.app.services.i10.b14_overlap_policy import evaluate_b14_overlap
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.delivery_readiness import notification_prefs_allow_scope
from backend.app.services.i10.policy_types import I10DecisionValue, I10SemanticFamily
from backend.app.services.notification_engine import _channel_for_type

logger = logging.getLogger(__name__)

I10_CANONICAL_POLICY_VERSION = "i10.b18.1"

_REASON_ALIASES = {
    "quiet_hours": "QUIET_HOURS_DEFER",
    "quiet_or_sleep_deferred": "QUIET_HOURS_DEFER",
    "active_conversation": "ACTIVE_CONVERSATION_DEFER",
    "active_conversation_deferred": "ACTIVE_CONVERSATION_DEFER",
    "feedback_suppressed": "FEEDBACK_NOT_NOW_SUPPRESS",
    "feedback_deferred": "FEEDBACK_TALK_LATER_DEFER",
    "user_preference_disabled": "USER_PREFERENCE_SUPPRESS",
    "critical_allowed": "CRITICAL_ALLOWED",
    "allowed": "POLICY_ALLOW",
    "do_not_notify": "DO_NOT_NOTIFY",
    "resolver_fail_open": "POLICY_FAIL_OPEN_ALLOW",
}

_SAFETY_FAMILIES = frozenset(
    {
        I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        I10SemanticFamily.SAFETY_ESCALATION.value,
    }
)

_B14_GAP_FAMILIES = frozenset(
    {
        I10SemanticFamily.CARE_DATA_GAP.value,
    }
)


@dataclass(frozen=True)
class I10CanonicalPolicyOutcome:
    decision: I10DecisionValue
    reason_code: str
    policy_version: str
    defer_until: Optional[datetime] = None
    gate4_action: Optional[str] = None
    gate4_reason: Optional[str] = None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def resolve_i10_policy_risk(
    candidate: I10NotificationCandidate,
    payload_metadata: Mapping[str, Any] | None,
) -> str:
    """Consume existing risk labels only — no inference from I9/RAG/LLM."""
    metadata = payload_metadata or {}
    explicit = metadata.get("risk_level") or metadata.get("risk")
    if explicit:
        return str(explicit).strip().lower()
    if candidate.semantic_family.value in _SAFETY_FAMILIES:
        return SmartNotificationRisk.CRITICAL.value
    priority = candidate.priority_hint or metadata.get("priority")
    if priority:
        from backend.app.services.gate4.policy_resolver import map_priority_to_risk

        return map_priority_to_risk(str(priority))
    return SmartNotificationRisk.NORMAL.value


def _normalize_reason(reason: str) -> str:
    key = (reason or "").strip().lower()
    return _REASON_ALIASES.get(key, reason.upper() if reason else "POLICY_UNKNOWN")


def _map_gate4_to_i10(action: str) -> I10DecisionValue:
    normalized = (action or "").strip().lower()
    if normalized == "allow":
        return I10DecisionValue.SEND
    if normalized == "defer":
        return I10DecisionValue.DEFER
    return I10DecisionValue.SUPPRESS


def evaluate_i10_canonical_policy(
    db: Session,
    *,
    candidate: I10NotificationCandidate,
    payload_metadata: Mapping[str, Any] | None = None,
    notification_type: str = "health_alert",
    channel: str | None = None,
    now_utc: Optional[datetime] = None,
) -> I10CanonicalPolicyOutcome:
    """
    Single effective I10 interruption policy decision.

    Order: expiry → B14 overlap → B06 prefs (fail-closed, including critical)
    → Gate4 resolver (feedback/quiet/active conversation) → normalized outcome.
    """
    effective_now = _ensure_utc(now_utc or datetime.now(timezone.utc))
    metadata = dict(payload_metadata or {})

    if candidate.expires_at is not None and candidate.expires_at <= effective_now:
        return I10CanonicalPolicyOutcome(
            decision=I10DecisionValue.EXPIRE,
            reason_code="CANDIDATE_EXPIRED",
            policy_version=I10_CANONICAL_POLICY_VERSION,
        )

    if candidate.semantic_family == I10SemanticFamily.CARE_STATUS_DIGEST:
        overlap = evaluate_b14_overlap(
            db,
            semantic_family=candidate.semantic_family,
            health_subject_id=candidate.health_subject_id,
            recipient_user_id=candidate.recipient_user_id,
            payload_metadata=metadata,
        )
        if overlap.suppress_status_digest:
            return I10CanonicalPolicyOutcome(
                decision=I10DecisionValue.SUPPRESS,
                reason_code=overlap.reason_code,
                policy_version=I10_CANONICAL_POLICY_VERSION,
            )

    prefs_ok, prefs_reason = notification_prefs_allow_scope(
        db,
        candidate.recipient_user_id,
        candidate.notification_scope,
    )
    if not prefs_ok:
        return I10CanonicalPolicyOutcome(
            decision=I10DecisionValue.SUPPRESS,
            reason_code=prefs_reason,
            policy_version=I10_CANONICAL_POLICY_VERSION,
        )

    risk = resolve_i10_policy_risk(candidate, metadata)
    category = map_notification_type_to_category(
        notification_type,
        {**metadata, "category": metadata.get("category")},
    )
    template_key = metadata.get("template_key")
    effective_channel = _channel_for_type(notification_type) or str(metadata.get("channel") or "push")

    try:
        resolved = resolve_notification_policy(
            db,
            user_id=candidate.recipient_user_id,
            risk=risk,
            category=str(category).strip().lower(),
            channel=effective_channel,
            now_utc=effective_now,
            template_key=str(template_key) if template_key else None,
            is_user_active_conversation=False,
        )
    except Exception:
        logger.exception(
            "[I10-B18] canonical_policy_fail_open candidate=%s recipient=%s",
            candidate.candidate_key,
            candidate.recipient_user_id,
        )
        return I10CanonicalPolicyOutcome(
            decision=I10DecisionValue.SEND,
            reason_code="POLICY_FAIL_OPEN_ALLOW",
            policy_version=I10_CANONICAL_POLICY_VERSION,
            gate4_action="allow",
            gate4_reason="resolver_fail_open",
        )

    gate_decision = resolved.decision
    i10_decision = _map_gate4_to_i10(gate_decision.action)
    reason_code = _normalize_reason(resolved.reason_code or gate_decision.reason)

    return I10CanonicalPolicyOutcome(
        decision=i10_decision,
        reason_code=reason_code,
        policy_version=I10_CANONICAL_POLICY_VERSION,
        defer_until=gate_decision.defer_until,
        gate4_action=gate_decision.action,
        gate4_reason=gate_decision.reason,
    )


def policy_version_label() -> str:
    return f"{I10_CANONICAL_POLICY_VERSION}+{GATE4D_POLICY_VERSION}"
