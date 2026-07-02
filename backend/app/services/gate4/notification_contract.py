"""
Gate 4B — Smart Notification Contract.

Pure contract/constants/helpers for notification types, actions, risk levels,
channels, localized labels, and push payload metadata. No DB, FCM, or scheduler I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Mapping, Optional, Sequence

GATE4_CONTRACT_VERSION: Final[str] = "4b.1"

# Policy constants (contract only; enforcement deferred to Gate 4D+).
NOT_NOW_SUPPRESS_HOURS: Final[int] = 24
TALK_LATER_DEFER_HOURS: Final[int] = 4
DEFAULT_DAILY_NOTIFICATION_TIME: Final[str] = "08:00"
V1_INTERACTION_CHANNEL: Final[str] = "text"
FUTURE_CHANNELS_SUPPORTED: Final[tuple[str, ...]] = ("voice", "call", "video")


class SmartNotificationAction(str, Enum):
    ACK_THANKS = "ACK_THANKS"
    NOT_NOW = "NOT_NOW"
    TALK_LATER = "TALK_LATER"
    OPEN_CHAT = "OPEN_CHAT"
    INLINE_REPLY = "INLINE_REPLY"
    START_VOICE = "START_VOICE"
    START_CALL = "START_CALL"
    START_VIDEO = "START_VIDEO"


class SmartNotificationRisk(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    INFORMATIONAL = "informational"
    DO_NOT_NOTIFY = "do_not_notify"


class SmartNotificationChannel(str, Enum):
    IN_APP = "in_app"
    PUSH = "push"
    CHAT = "chat"
    VOICE = "voice"
    CALL = "call"
    VIDEO = "video"


class SmartNotificationCategory(str, Enum):
    DAILY = "daily"
    REMINDER = "reminder"
    CARE_FOLLOW_UP = "care_follow_up"
    HEALTH_ALERT = "health_alert"
    MEDICATION = "medication"
    DEVICE = "device"
    ENGAGEMENT = "engagement"
    COMPANION = "companion"
    SYSTEM = "system"
    KNOWLEDGE = "knowledge"
    SAFETY = "safety"


class SmartNotificationLanguage(str, Enum):
    FA = "fa"
    EN = "en"
    AR = "ar"


V1_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        SmartNotificationAction.ACK_THANKS.value,
        SmartNotificationAction.NOT_NOW.value,
        SmartNotificationAction.TALK_LATER.value,
        SmartNotificationAction.OPEN_CHAT.value,
    }
)

FUTURE_ONLY_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        SmartNotificationAction.INLINE_REPLY.value,
        SmartNotificationAction.START_VOICE.value,
        SmartNotificationAction.START_CALL.value,
        SmartNotificationAction.START_VIDEO.value,
    }
)

V1_DEFAULT_ACTIONS: Final[tuple[str, ...]] = (
    SmartNotificationAction.ACK_THANKS.value,
    SmartNotificationAction.NOT_NOW.value,
    SmartNotificationAction.TALK_LATER.value,
    SmartNotificationAction.OPEN_CHAT.value,
)

SUPPORTED_LANGUAGES: Final[frozenset[str]] = frozenset(lang.value for lang in SmartNotificationLanguage)
DEFAULT_LANGUAGE: Final[str] = SmartNotificationLanguage.EN.value

ACTION_LABELS: Final[Mapping[str, Mapping[str, str]]] = {
    SmartNotificationAction.ACK_THANKS.value: {
        SmartNotificationLanguage.FA.value: "متوجه شدم، ممنون",
        SmartNotificationLanguage.EN.value: "Got it, thanks",
        SmartNotificationLanguage.AR.value: "فهمت، شكرًا",
    },
    SmartNotificationAction.NOT_NOW.value: {
        SmartNotificationLanguage.FA.value: "الان نیازی نیست",
        SmartNotificationLanguage.EN.value: "Not now",
        SmartNotificationLanguage.AR.value: "ليس الآن",
    },
    SmartNotificationAction.TALK_LATER.value: {
        SmartNotificationLanguage.FA.value: "بعداً صحبت می‌کنیم",
        SmartNotificationLanguage.EN.value: "Let's talk later",
        SmartNotificationLanguage.AR.value: "نتحدث لاحقًا",
    },
    SmartNotificationAction.OPEN_CHAT.value: {
        SmartNotificationLanguage.FA.value: "صحبت کنیم",
        SmartNotificationLanguage.EN.value: "Let's talk",
        SmartNotificationLanguage.AR.value: "لنتحدث",
    },
}

LEGACY_ACTION_MAP: Final[Mapping[str, str]] = {
    "open_chat": SmartNotificationAction.OPEN_CHAT.value,
    "open": SmartNotificationAction.OPEN_CHAT.value,
    "like": SmartNotificationAction.ACK_THANKS.value,
    "dislike": SmartNotificationAction.NOT_NOW.value,
    "dismiss": SmartNotificationAction.NOT_NOW.value,
}


@dataclass(frozen=True)
class ActionSemantics:
    """Documented semantics for a canonical notification action."""

    action_id: str
    description: str
    closes_notification: bool = False
    suppress_hours: Optional[int] = None
    defer_hours: Optional[int] = None
    opens_chat: bool = False
    passes_source_notification_id: bool = False
    future_only: bool = False


_ACTION_SEMANTICS: Final[Mapping[str, ActionSemantics]] = {
    SmartNotificationAction.ACK_THANKS.value: ActionSemantics(
        action_id=SmartNotificationAction.ACK_THANKS.value,
        description="User acknowledges the notification; closes without opening chat.",
        closes_notification=True,
    ),
    SmartNotificationAction.NOT_NOW.value: ActionSemantics(
        action_id=SmartNotificationAction.NOT_NOW.value,
        description="Suppress similar follow-up for a short period.",
        closes_notification=True,
        suppress_hours=NOT_NOW_SUPPRESS_HOURS,
    ),
    SmartNotificationAction.TALK_LATER.value: ActionSemantics(
        action_id=SmartNotificationAction.TALK_LATER.value,
        description="Defer similar follow-up to a later time.",
        closes_notification=True,
        defer_hours=TALK_LATER_DEFER_HOURS,
    ),
    SmartNotificationAction.OPEN_CHAT.value: ActionSemantics(
        action_id=SmartNotificationAction.OPEN_CHAT.value,
        description="Open main chat and pass source_notification_id/context.",
        opens_chat=True,
        passes_source_notification_id=True,
    ),
    SmartNotificationAction.INLINE_REPLY.value: ActionSemantics(
        action_id=SmartNotificationAction.INLINE_REPLY.value,
        description="User replies inline from notification UI (V2+).",
        future_only=True,
    ),
    SmartNotificationAction.START_VOICE.value: ActionSemantics(
        action_id=SmartNotificationAction.START_VOICE.value,
        description="Start a voice interaction session (V2+).",
        future_only=True,
    ),
    SmartNotificationAction.START_CALL.value: ActionSemantics(
        action_id=SmartNotificationAction.START_CALL.value,
        description="Start a phone call flow (V2+).",
        future_only=True,
    ),
    SmartNotificationAction.START_VIDEO.value: ActionSemantics(
        action_id=SmartNotificationAction.START_VIDEO.value,
        description="Start a video interaction session (V2+).",
        future_only=True,
    ),
}


def normalize_language(language: str) -> str:
    """Return a supported language code; unsupported values fall back to ``en``."""
    if not language:
        return DEFAULT_LANGUAGE
    normalized = language.strip().lower().split("-")[0]
    if normalized in SUPPORTED_LANGUAGES:
        return normalized
    return DEFAULT_LANGUAGE


def is_v1_action(action: str) -> bool:
    return action in V1_ACTIONS


def is_future_only_action(action: str) -> bool:
    return action in FUTURE_ONLY_ACTIONS


def get_action_semantics(action: str) -> ActionSemantics:
    """Return semantics for a canonical action; raises ValueError if unknown."""
    canonical = normalize_legacy_action(action) if action in LEGACY_ACTION_MAP else action
    try:
        return _ACTION_SEMANTICS[canonical]
    except KeyError as exc:
        raise ValueError(f"Unknown notification action: {action}") from exc


def get_action_label(action: str, language: str) -> str:
    """
    Return localized label for a V1 action.

    Unsupported language falls back to ``en``. Unknown action raises ValueError.
    Future-only actions raise ValueError (labels not defined for V1 push).
    """
    canonical = normalize_legacy_action(action) if action in LEGACY_ACTION_MAP else action
    if canonical not in ACTION_LABELS:
        raise ValueError(f"No label defined for action: {action}")
    lang = normalize_language(language)
    return ACTION_LABELS[canonical][lang]


def can_bypass_quiet_hours(risk: str) -> bool:
    """Only ``critical`` risk may bypass quiet/sleep hours in V1."""
    return risk == SmartNotificationRisk.CRITICAL.value


def should_notify_for_risk(risk: str) -> bool:
    """``do_not_notify`` must not be enqueued/delivered; all other V1 risks may notify."""
    return risk != SmartNotificationRisk.DO_NOT_NOTIFY.value


def normalize_legacy_action(action: str) -> str:
    """
    Map legacy feedback/action strings to canonical Gate 4 action IDs.

    Mapping (backward-compatible, not wired to runtime yet):
    - open_chat / open -> OPEN_CHAT
    - like -> ACK_THANKS
    - dislike / dismiss -> NOT_NOW

    Already-canonical action IDs pass through unchanged.
  """
    if not action:
        raise ValueError("action must be non-empty")
    key = action.strip()
    lowered = key.lower()
    if lowered in LEGACY_ACTION_MAP:
        return LEGACY_ACTION_MAP[lowered]
    if key in _ACTION_SEMANTICS:
        return key
    raise ValueError(f"Unknown legacy or canonical action: {action}")


def _resolve_actions(action_ids: Optional[Sequence[str]], language: str) -> list[dict[str, str]]:
    ids = list(action_ids) if action_ids is not None else list(V1_DEFAULT_ACTIONS)
    resolved: list[dict[str, str]] = []
    for action_id in ids:
        resolved.append(
            {
                "action_id": action_id,
                "label": get_action_label(action_id, language),
                "future_only": str(is_future_only_action(action_id)).lower(),
            }
        )
    return resolved


def build_smart_notification_metadata(
    *,
    notification_id: int | None,
    category: str,
    risk: str,
    language: str,
    source_notification_id: int | None = None,
    source_type: str | None = None,
    source_id: str | int | None = None,
    deeplink_url: str | None = None,
    actions: list[str] | None = None,
) -> dict[str, Any]:
    """
  Build Gate 4 push/inbox metadata dictionary. Pure function — no I/O.

  Does not send push, write DB, or call FCM.
  """
    lang = normalize_language(language)
    metadata: dict[str, Any] = {
        "gate": "gate4",
        "contract_version": GATE4_CONTRACT_VERSION,
        "category": category,
        "risk": risk,
        "language": lang,
        "interaction_channel": V1_INTERACTION_CHANNEL,
        "future_channels_supported": list(FUTURE_CHANNELS_SUPPORTED),
        "quiet_bypass": can_bypass_quiet_hours(risk),
        "should_notify": should_notify_for_risk(risk),
        "actions": _resolve_actions(actions, lang),
        "policy": {
            "not_now_suppress_hours": NOT_NOW_SUPPRESS_HOURS,
            "talk_later_defer_hours": TALK_LATER_DEFER_HOURS,
            "default_daily_notification_time": DEFAULT_DAILY_NOTIFICATION_TIME,
        },
    }
    if notification_id is not None:
        metadata["notification_id"] = notification_id
    if source_notification_id is not None:
        metadata["source_notification_id"] = source_notification_id
    if source_type is not None:
        metadata["source_type"] = source_type
    if source_id is not None:
        metadata["source_id"] = str(source_id)
    if deeplink_url is not None:
        metadata["deeplink_url"] = deeplink_url
    return metadata
