"""I10-B18 canonical interruption policy — Gate4 reuse + B14 overlap + B05/B06 boundary."""

from __future__ import annotations

import json
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
from backend.app.services.i10.care_safety_copy import CARE_SAFETY_POLICY_RISK_SOURCE
from backend.app.services.i10.contracts import I10NotificationCandidate
from backend.app.services.i10.delivery_readiness import notification_prefs_allow_scope
from backend.app.services.i10.policy_types import I10DecisionValue, I10SemanticFamily
from backend.app.services.notification_engine import _channel_for_type

logger = logging.getLogger(__name__)

I10_CANONICAL_POLICY_VERSION = "i10.b18.2"

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

# CR-04E2 — I6 interruption prefs accepted only as typed suppress inputs.
_I6_INTERRUPTION_PROVENANCE = frozenset({"USER_STATED", "USER_CONFIRMED"})
_I6_BLOCKED_SENSITIVITY = frozenset({"high", "critical"})
_FOLLOW_UP_PREF_KEY = "follow_up_preference"
_PROACTIVE_PREF_KEY = "proactive_checkin_preference"
_PROACTIVE_SUPPRESS_FAMILIES = frozenset(
    {
        I10SemanticFamily.PRESENCE_REENGAGEMENT,
        I10SemanticFamily.ENGAGEMENT_NUDGE,
    }
)

USER_FOLLOW_UP_PREFERENCE_SUPPRESS = "USER_FOLLOW_UP_PREFERENCE_SUPPRESS"
USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS = "USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS"


def _authorized_critical_policy_risk(metadata: Mapping[str, Any]) -> Optional[str]:
    """Accept CRITICAL only when B16 source contract explicitly provides it."""
    policy_risk = metadata.get("policy_risk_level")
    if not policy_risk:
        return None
    risk = str(policy_risk).strip().lower()
    if risk != SmartNotificationRisk.CRITICAL.value:
        return risk
    source = str(metadata.get("policy_risk_source") or "").strip()
    if source == CARE_SAFETY_POLICY_RISK_SOURCE:
        return risk
    return None


def resolve_i10_policy_risk(
    candidate: I10NotificationCandidate,
    payload_metadata: Mapping[str, Any] | None,
) -> str:
    """Consume explicit upstream interruption policy risk only — no semantic inference."""
    metadata = payload_metadata or {}
    authorized_critical = _authorized_critical_policy_risk(metadata)
    if authorized_critical is not None:
        return authorized_critical
    explicit = metadata.get("risk_level") or metadata.get("risk")
    if explicit:
        return str(explicit).strip().lower()
    priority = candidate.priority_hint or metadata.get("priority")
    if priority:
        from backend.app.services.gate4.policy_resolver import map_priority_to_risk

        return map_priority_to_risk(str(priority))
    return SmartNotificationRisk.NORMAL.value


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


def _read_typed_boolean_preference(
    db: Session,
    *,
    recipient_user_id: int,
    key: str,
) -> Optional[bool]:
    """Read one canonical I6 preference as a typed bool, or None when unsupported.

    Accepts only active/readable USER_STATED|USER_CONFIRMED facts whose decoded
    value_json is an actual JSON boolean. High/critical, system-derived,
    unknown provenance, and non-boolean values are ignored (fail open to
    existing I10 policy). Never returns raw values for copy/LLM.
    """
    from backend.app.services.i6.memory_writes import get_readable_fact_or_none

    row = get_readable_fact_or_none(db, recipient_user_id, "preferences", key)
    if row is None:
        return None
    provenance = str(getattr(row, "provenance_class", "") or "").strip()
    if provenance not in _I6_INTERRUPTION_PROVENANCE:
        return None
    sensitivity = str(getattr(row, "sensitivity_class", "") or "").strip().lower()
    if sensitivity in _I6_BLOCKED_SENSITIVITY:
        return None
    raw = getattr(row, "value_json", None)
    if raw is None:
        return None
    try:
        decoded = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, bool):
        return None
    return decoded


def _user_interruption_preference_suppress(
    db: Session,
    candidate: I10NotificationCandidate,
) -> Optional[I10CanonicalPolicyOutcome]:
    """False-only suppressions from typed I6 interruption preferences.

    True never forces SEND — it only means this rule does not suppress.
    Families outside the explicit maps are never suppressed by these prefs.
    """
    family = candidate.semantic_family

    if family == I10SemanticFamily.GENERAL_CONTEXTUAL_FOLLOW_UP:
        follow_up = _read_typed_boolean_preference(
            db,
            recipient_user_id=candidate.recipient_user_id,
            key=_FOLLOW_UP_PREF_KEY,
        )
        if follow_up is False:
            return I10CanonicalPolicyOutcome(
                decision=I10DecisionValue.SUPPRESS,
                reason_code=USER_FOLLOW_UP_PREFERENCE_SUPPRESS,
                policy_version=I10_CANONICAL_POLICY_VERSION,
            )

    if family in _PROACTIVE_SUPPRESS_FAMILIES:
        proactive = _read_typed_boolean_preference(
            db,
            recipient_user_id=candidate.recipient_user_id,
            key=_PROACTIVE_PREF_KEY,
        )
        if proactive is False:
            return I10CanonicalPolicyOutcome(
                decision=I10DecisionValue.SUPPRESS,
                reason_code=USER_PROACTIVE_CHECKIN_PREFERENCE_SUPPRESS,
                policy_version=I10_CANONICAL_POLICY_VERSION,
            )

    return None


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

    Order: expiry → B14 overlap → CR-04E2 I6 interruption prefs (false-only)
    → B06 prefs (fail-closed, including critical)
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

    pref_suppress = _user_interruption_preference_suppress(db, candidate)
    if pref_suppress is not None:
        return pref_suppress

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
