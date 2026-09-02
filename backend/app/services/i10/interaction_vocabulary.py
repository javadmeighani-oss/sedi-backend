"""I10-B17 — canonical notification interaction vocabulary (domain-safe semantics)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from backend.app.models import Notification
from backend.app.services.gate4.notification_contract import SmartNotificationAction
from backend.app.services.i10.policy_types import I10SemanticFamily

VOCABULARY_VERSION = "I10_INTERACTION_VOCABULARY_V1"

BOUNDED_DISLIKE_REASONS = frozenset(
    {
        "too_frequent",
        "irrelevant",
        "unclear",
        "not_helpful",
        "wrong_timing",
    }
)


class CanonicalInteractionVerb(str, Enum):
    ACKNOWLEDGE = "ACKNOWLEDGE"
    LIKE = "LIKE"
    DISLIKE = "DISLIKE"
    DISLIKE_REASON = "DISLIKE_REASON"
    TALK_TO_SEDI = "TALK_TO_SEDI"
    READ = "READ"
    NOT_NOW = "NOT_NOW"
    TALK_LATER = "TALK_LATER"
    DONE = "DONE"


CANONICAL_VERB_TO_EVENT_TYPE: dict[CanonicalInteractionVerb, str] = {
    CanonicalInteractionVerb.ACKNOWLEDGE: "notification_ack",
    CanonicalInteractionVerb.LIKE: "notification_like",
    CanonicalInteractionVerb.DISLIKE: "notification_dislike",
    CanonicalInteractionVerb.DISLIKE_REASON: "notification_dislike_reason",
    CanonicalInteractionVerb.TALK_TO_SEDI: "notification_open_chat",
    CanonicalInteractionVerb.READ: "notification_read",
    CanonicalInteractionVerb.NOT_NOW: "notification_not_now",
    CanonicalInteractionVerb.TALK_LATER: "notification_talk_later",
    CanonicalInteractionVerb.DONE: "notification_done",
}

CANONICAL_VERB_TO_FEEDBACK_ACTION: dict[CanonicalInteractionVerb, str] = {
    CanonicalInteractionVerb.ACKNOWLEDGE: "acknowledge",
    CanonicalInteractionVerb.LIKE: "like",
    CanonicalInteractionVerb.DISLIKE: "dislike",
    CanonicalInteractionVerb.DISLIKE_REASON: "dislike",
    CanonicalInteractionVerb.TALK_TO_SEDI: "open_chat",
    CanonicalInteractionVerb.READ: "read",
    CanonicalInteractionVerb.NOT_NOW: "dismissed",
    CanonicalInteractionVerb.TALK_LATER: "dismissed",
    CanonicalInteractionVerb.DONE: "done",
}

VERB_TO_GATE4_POLICY_ACTION: dict[CanonicalInteractionVerb, str] = {
    CanonicalInteractionVerb.ACKNOWLEDGE: SmartNotificationAction.ACK_THANKS.value,
    CanonicalInteractionVerb.NOT_NOW: SmartNotificationAction.NOT_NOW.value,
    CanonicalInteractionVerb.TALK_LATER: SmartNotificationAction.TALK_LATER.value,
    CanonicalInteractionVerb.TALK_TO_SEDI: SmartNotificationAction.OPEN_CHAT.value,
}

GENERIC_VERBS_WITHOUT_DOMAIN_COMPLETION = frozenset(
    {
        CanonicalInteractionVerb.ACKNOWLEDGE,
        CanonicalInteractionVerb.LIKE,
        CanonicalInteractionVerb.DISLIKE,
        CanonicalInteractionVerb.DISLIKE_REASON,
        CanonicalInteractionVerb.TALK_TO_SEDI,
        CanonicalInteractionVerb.READ,
        CanonicalInteractionVerb.NOT_NOW,
        CanonicalInteractionVerb.TALK_LATER,
    }
)

MEDICATION_CONFIRM_AUTHORITY = "B09_MEDICATION_CONFIRM_TAKEN_ENDPOINT"
APPOINTMENT_ATTENDANCE_AUTHORITY = "NONE_GENERIC"
I8_ACTION_COMPLETION_AUTHORITY = "I8_OPERATIONAL_PLAN_ACTION_DOMAIN"
CARE_ACTION_COMPLETION_AUTHORITY = "B15_I8_MANAGED_ACTION_DOMAIN"
SAFETY_RESOLUTION_AUTHORITY = "SECTION10_I4_PROVENANCE_SEPARATE"


@dataclass(frozen=True)
class ResolvedInteraction:
    verb: CanonicalInteractionVerb
    feedback_action: str
    reason: Optional[str]
    dislike_reason_bounded: bool
    gate4_policy_action: Optional[str]


def _bounded_reason(raw: Optional[str]) -> tuple[Optional[str], bool]:
    if raw is None:
        return None, False
    cleaned = str(raw).strip()[:64]
    if not cleaned:
        return None, False
    return cleaned, cleaned in BOUNDED_DISLIKE_REASONS


def resolve_interaction_verb(payload: Mapping[str, Any]) -> ResolvedInteraction:
    """Map contract/legacy payload to canonical interaction verb without domain inference."""
    reaction = payload.get("reaction")
    action_id = payload.get("action_id")
    action_legacy = payload.get("action")
    feedback_legacy = payload.get("feedback")
    reason, reason_bounded = _bounded_reason(payload.get("reason"))

    if action_id:
        key = str(action_id).strip()
        lowered = key.lower()
        if key in SmartNotificationAction._value2member_map_:
            verb = {
                SmartNotificationAction.ACK_THANKS.value: CanonicalInteractionVerb.ACKNOWLEDGE,
                SmartNotificationAction.NOT_NOW.value: CanonicalInteractionVerb.NOT_NOW,
                SmartNotificationAction.TALK_LATER.value: CanonicalInteractionVerb.TALK_LATER,
                SmartNotificationAction.OPEN_CHAT.value: CanonicalInteractionVerb.TALK_TO_SEDI,
            }[key]
        elif lowered in ("open_chat", "open"):
            verb = CanonicalInteractionVerb.TALK_TO_SEDI
        elif lowered == "done":
            verb = CanonicalInteractionVerb.DONE
        elif lowered == "like":
            verb = CanonicalInteractionVerb.LIKE
        elif lowered == "dislike":
            verb = (
                CanonicalInteractionVerb.DISLIKE_REASON
                if reason
                else CanonicalInteractionVerb.DISLIKE
            )
        else:
            verb = CanonicalInteractionVerb.ACKNOWLEDGE
    elif reaction == "like":
        verb = CanonicalInteractionVerb.LIKE
    elif reaction == "dislike":
        verb = (
            CanonicalInteractionVerb.DISLIKE_REASON
            if reason
            else CanonicalInteractionVerb.DISLIKE
        )
    elif reaction == "dismiss":
        verb = CanonicalInteractionVerb.NOT_NOW
    elif reaction in ("seen", "interact"):
        verb = CanonicalInteractionVerb.READ
    elif action_legacy in ("like", "dislike", "open_chat", "dismissed"):
        verb = {
            "like": CanonicalInteractionVerb.LIKE,
            "dislike": (
                CanonicalInteractionVerb.DISLIKE_REASON
                if reason
                else CanonicalInteractionVerb.DISLIKE
            ),
            "open_chat": CanonicalInteractionVerb.TALK_TO_SEDI,
            "dismissed": CanonicalInteractionVerb.NOT_NOW,
        }[action_legacy]
    elif feedback_legacy == "positive":
        verb = CanonicalInteractionVerb.LIKE
    elif feedback_legacy == "negative":
        verb = (
            CanonicalInteractionVerb.DISLIKE_REASON
            if reason
            else CanonicalInteractionVerb.DISLIKE
        )
    elif feedback_legacy == "neutral":
        verb = CanonicalInteractionVerb.READ
    else:
        verb = CanonicalInteractionVerb.READ

    return ResolvedInteraction(
        verb=verb,
        feedback_action=CANONICAL_VERB_TO_FEEDBACK_ACTION[verb],
        reason=reason,
        dislike_reason_bounded=reason_bounded,
        gate4_policy_action=VERB_TO_GATE4_POLICY_ACTION.get(verb),
    )


def event_type_for_verb(verb: CanonicalInteractionVerb) -> str:
    return CANONICAL_VERB_TO_EVENT_TYPE[verb]


def semantic_family_for_notification(notification: Notification) -> Optional[str]:
    return getattr(notification, "semantic_family", None)


def domain_completion_authority_for_notification(
    notification: Notification,
) -> Optional[str]:
    family = semantic_family_for_notification(notification)
    if family in (
        I10SemanticFamily.MEDICATION_DUE.value,
        I10SemanticFamily.MEDICATION_FOLLOW_UP.value,
    ):
        return MEDICATION_CONFIRM_AUTHORITY
    if family in (
        I10SemanticFamily.DOCTOR_APPOINTMENT_REMINDER.value,
        I10SemanticFamily.LAB_APPOINTMENT_REMINDER.value,
        I10SemanticFamily.MEDICAL_EVENT_REMINDER.value,
    ):
        return APPOINTMENT_ATTENDANCE_AUTHORITY
    if family in (
        I10SemanticFamily.LIFESTYLE_ROUTINE_COACHING.value,
        I10SemanticFamily.NUTRITION_PLAN_FOLLOW_UP.value,
        I10SemanticFamily.EXERCISE_PLAN_FOLLOW_UP.value,
    ):
        return I8_ACTION_COMPLETION_AUTHORITY
    if family == I10SemanticFamily.CARE_ACTION.value:
        return CARE_ACTION_COMPLETION_AUTHORITY
    if family in (
        I10SemanticFamily.CARE_SAFETY_ESCALATION.value,
        I10SemanticFamily.SAFETY_ESCALATION.value,
    ):
        return SAFETY_RESOLUTION_AUTHORITY
    return None


def assert_generic_verb_cannot_complete_domain(
    notification: Notification,
    verb: CanonicalInteractionVerb,
) -> None:
    """Ledger-only guard: generic verbs never imply governed domain completion."""
    if verb is CanonicalInteractionVerb.DONE:
        raise ValueError("done_requires_domain_authority")
    if verb not in GENERIC_VERBS_WITHOUT_DOMAIN_COMPLETION:
        return
    _ = domain_completion_authority_for_notification(notification)
