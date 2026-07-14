"""
Gate 4E — FCM push payload contract (Android V1).

Pure helpers: no DB writes, no FCM calls, no scheduler. Builds additive Gate 4
data keys for FCMAdapter while preserving legacy FCM data fields.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence

from backend.app.services.gate4.notification_contract import (
    GATE4_CONTRACT_VERSION,
    V1_DEFAULT_ACTIONS,
    can_bypass_quiet_hours,
    get_action_label,
    is_future_only_action,
    is_v1_action,
    normalize_language,
    should_notify_for_risk,
)

GATE4E_PUSH_CONTRACT_VERSION: str = "4e.1"
SUPPORTED_LANGUAGES_CSV: str = "fa,en,ar"
ICON_POLICY: str = "icons_static_text_localized"
FEEDBACK_PATH_TEMPLATE: str = "/notifications/{notification_id}/feedback"

# Categories that map to the reminder Android channel.
_REMINDER_CHANNEL_CATEGORIES = frozenset({"reminder", "medication", "care_follow_up"})


def normalize_push_language(language: str | None) -> str:
    """Normalize user language for push payload; unsupported values fall back to ``en``."""
    return normalize_language(language or "")


def _coerce_fcm_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)[:1024]


def _resolve_v1_action_ids(actions: Sequence[str] | None, *, include_future: bool = False) -> list[str]:
    ids = list(actions) if actions is not None else list(V1_DEFAULT_ACTIONS)
    resolved: list[str] = []
    for action_id in ids:
        if is_future_only_action(action_id) and not include_future:
            continue
        if not include_future and not is_v1_action(action_id):
            continue
        resolved.append(action_id)
    return resolved


def _resolve_gate4_actions(actions: Sequence[str] | None, language: str, *, include_future: bool = False) -> list[dict[str, str]]:
    lang = normalize_push_language(language)
    resolved: list[dict[str, str]] = []
    for action_id in _resolve_v1_action_ids(actions, include_future=include_future):
        try:
            label = get_action_label(action_id, lang)
        except ValueError:
            if include_future and is_future_only_action(action_id):
                label = action_id
            else:
                raise
        resolved.append(
            {
                "action_id": action_id,
                "label": label,
                "feedback_reaction": "interact",
            }
        )
    return resolved


def build_gate4_deeplink(
    *,
    notification_id: int | None = None,
    source_notification_id: int | None = None,
    action_id: str | None = None,
    conversation_id: str | None = None,
) -> str:
    """
    Build ``sedi://chat?...`` deeplink without secrets or long free text.

    Prefers ``source_notification_id`` when both source and notification ids are set.
    """
    params: list[str] = ["from=notif"]
    if source_notification_id is not None:
        params.append(f"source_notification_id={int(source_notification_id)}")
    elif notification_id is not None:
        params.append(f"id={int(notification_id)}")
    if action_id:
        params.append(f"action_id={action_id.strip()}")
    if conversation_id:
        params.append(f"conversation_id={conversation_id.strip()[:128]}")
    return "sedi://chat?" + "&".join(params)


def build_gate4_android_notification_options(
    *,
    risk: str,
    priority: str | None,
    category: str,
    sound_enabled: bool = True,
) -> dict[str, Any]:
    """
    Android channel/sound/priority contract for V1 FCM (data-side metadata).

    ``alarm_like`` is ``true`` only for ``critical`` risk in V1.
    """
    risk_key = (risk or "normal").strip().lower()
    category_key = (category or "system").strip().lower()
    priority_key = (priority or "normal").strip().lower()

    if risk_key == "critical":
        channel_id = "sedi_critical"
        sound = "sedi_critical_alert" if sound_enabled else ""
        android_priority = "high"
        critical = True
        alarm_like = True
        visibility = "public"
    elif category_key in ("health_alert", "health_status") or risk_key == "high" or priority_key in ("high", "critical"):
        channel_id = "sedi_health"
        sound = "sedi_notification" if sound_enabled else ""
        android_priority = "high"
        critical = False
        alarm_like = False
        visibility = "public"
    elif category_key in _REMINDER_CHANNEL_CATEGORIES:
        channel_id = "sedi_reminder"
        sound = "sedi_notification" if sound_enabled else ""
        android_priority = "normal"
        critical = False
        alarm_like = False
        visibility = "private"
    else:
        channel_id = "sedi_default"
        sound = "sedi_notification" if sound_enabled else ""
        android_priority = "normal"
        critical = False
        alarm_like = False
        visibility = "private"

    return {
        "android_priority": android_priority,
        "channel_id": channel_id,
        "sound": sound or None,
        "visibility": visibility,
        "critical": critical,
        "alarm_like": alarm_like,
    }


def build_gate4_push_data_payload(
    *,
    notification_id: int | None,
    user_id: int | None,
    title: str | None,
    body: str | None,
    category: str,
    risk: str,
    priority: str | None,
    language: str,
    deeplink_url: str | None,
    source_notification_id: int | None = None,
    source_type: str | None = None,
    source_id: str | int | None = None,
    template_key: str | None = None,
    include_source_refs: bool = False,
    actions: list[str] | None = None,
    interaction_channel: str = "text",
    include_future_actions: bool = False,
) -> dict[str, str]:
    """
    Build Gate 4 FCM **data** payload fields (all string values).

    ``gate4_actions`` holds JSON-serialized V1 actions with localized labels.
    Legacy ``actions`` (raw ``actions_json``) is preserved by the FCMAdapter merge helper.
    """
    lang = normalize_push_language(language)
    gate4_actions = _resolve_gate4_actions(actions, lang, include_future=include_future_actions)
    action_labels = {item["action_id"]: item["label"] for item in gate4_actions}

    payload: dict[str, str] = {
        "gate": "gate4",
        "contract_version": GATE4E_PUSH_CONTRACT_VERSION,
        "gate4_contract_version": GATE4_CONTRACT_VERSION,
        "category": _coerce_fcm_string(category),
        "gate4_category": _coerce_fcm_string(category),
        "risk": _coerce_fcm_string(risk),
        "gate4_risk_level": _coerce_fcm_string(risk),
        "priority": _coerce_fcm_string(priority or "normal"),
        "language": lang,
        "interaction_channel": _coerce_fcm_string(interaction_channel),
        "quiet_bypass": _coerce_fcm_string(can_bypass_quiet_hours(risk)),
        "should_notify": _coerce_fcm_string(should_notify_for_risk(risk)),
        "icon_policy": ICON_POLICY,
        "supported_languages": SUPPORTED_LANGUAGES_CSV,
        "gate4_actions": json.dumps(gate4_actions, ensure_ascii=False, separators=(",", ":")),
        "action_labels": json.dumps(action_labels, ensure_ascii=False, separators=(",", ":")),
    }

    if notification_id is not None:
        payload["notification_id"] = _coerce_fcm_string(notification_id)
        payload["feedback_path"] = FEEDBACK_PATH_TEMPLATE.format(notification_id=notification_id)
    if user_id is not None:
        payload["user_id"] = _coerce_fcm_string(user_id)
    if title:
        payload["title"] = _coerce_fcm_string(title)
    if body:
        payload["body"] = _coerce_fcm_string(body)
    if deeplink_url:
        payload["deeplink_url"] = _coerce_fcm_string(deeplink_url)
    if source_notification_id is not None:
        payload["source_notification_id"] = _coerce_fcm_string(source_notification_id)
    if include_source_refs:
        if source_type is not None:
            payload["source_type"] = _coerce_fcm_string(source_type)
        if source_id is not None:
            payload["source_id"] = _coerce_fcm_string(source_id)
    if template_key:
        payload["template_key"] = _coerce_fcm_string(template_key)
        payload["gate4_template_key"] = _coerce_fcm_string(template_key)

    android_opts = build_gate4_android_notification_options(
        risk=risk,
        priority=priority,
        category=category,
    )
    for key in ("android_priority", "channel_id", "sound", "visibility", "critical", "alarm_like"):
        value = android_opts.get(key)
        if value is not None and value != "":
            payload[key] = _coerce_fcm_string(value)

    return payload


def merge_gate4_into_fcm_data(
    legacy_data: Mapping[str, str],
    gate4_data: Mapping[str, str],
) -> dict[str, str]:
    """
    Merge Gate 4 keys additively into legacy FCM data.

    Existing legacy keys (``notification_id``, ``channel``, ``type``, ``deeplink_url``,
    ``actions``) are never overwritten.
    """
    merged = dict(legacy_data)
    for key, value in gate4_data.items():
        if key not in merged:
            merged[key] = value
    return merged


def enrich_notification_fcm_data(
    *,
    legacy_data: Mapping[str, str],
    notification_id: int,
    user_id: int,
    title: str | None,
    body: str | None,
    notification_type: str,
    priority: str | None,
    language: str | None,
    deeplink_url: str | None,
    actions_json: str | None,
    category: str | None = None,
    risk: str | None = None,
    template_key: str | None = None,
    source_notification_id: int | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """
    Build merged FCM data + Android options for FCMAdapter.

    Uses ``map_*`` helpers from notification_context when category/risk are omitted.
    Does not expose source_type/source_id in mobile payload by default.
    """
    from backend.app.services.gate4.notification_context import (
        map_notification_type_to_category,
        map_priority_to_risk_level,
    )

    resolved_category = category or map_notification_type_to_category(notification_type)
    resolved_risk = risk or map_priority_to_risk_level(priority or "normal")
    resolved_lang = normalize_push_language(language)
    resolved_deeplink = deeplink_url or build_gate4_deeplink(
        notification_id=notification_id,
        source_notification_id=source_notification_id,
    )

    gate4_data = build_gate4_push_data_payload(
        notification_id=notification_id,
        user_id=user_id,
        title=title,
        body=body,
        category=resolved_category,
        risk=resolved_risk,
        priority=priority,
        language=resolved_lang,
        deeplink_url=resolved_deeplink,
        source_notification_id=source_notification_id or notification_id,
        template_key=template_key,
        include_source_refs=False,
    )
    merged = merge_gate4_into_fcm_data(legacy_data, gate4_data)
    android_opts = build_gate4_android_notification_options(
        risk=resolved_risk,
        priority=priority,
        category=resolved_category,
    )
    return merged, android_opts
