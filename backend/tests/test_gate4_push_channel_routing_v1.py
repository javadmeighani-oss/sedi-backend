"""Gate 4 Android channel routing unit tests (G1 versioned channels + sedi_alarm)."""

from __future__ import annotations

from backend.app.services.gate4.notification_contract import (
    ACTION_LABELS,
    SmartNotificationAction,
    build_smart_notification_metadata,
    get_action_label,
    normalize_language,
)
from backend.app.services.gate4.push_payload import (
    CANONICAL_SEDI_SOUND,
    CHANNEL_ENGAGEMENT_V2,
    CHANNEL_HEALTH_ALERT_V2,
    CHANNEL_MORNING_V2,
    build_gate4_android_notification_options,
    build_gate4_push_data_payload,
    normalize_push_language,
)


def test_health_status_maps_to_health_alert_v2():
    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="health_status",
    )
    assert opts["channel_id"] == CHANNEL_HEALTH_ALERT_V2
    assert opts["sound"] == CANONICAL_SEDI_SOUND
    assert opts["android_priority"] == "high"
    assert opts["critical"] is False


def test_health_alert_maps_to_health_alert_v2():
    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="health_alert",
    )
    assert opts["channel_id"] == CHANNEL_HEALTH_ALERT_V2
    assert opts["sound"] == CANONICAL_SEDI_SOUND
    assert opts["android_priority"] == "high"


def test_critical_maps_to_health_alert_v2_with_alarm_like():
    opts = build_gate4_android_notification_options(
        risk="critical",
        priority="critical",
        category="health_alert",
    )
    assert opts["channel_id"] == CHANNEL_HEALTH_ALERT_V2
    assert opts["sound"] == CANONICAL_SEDI_SOUND
    assert opts["android_priority"] == "high"
    assert opts["critical"] is True
    assert opts["alarm_like"] is True


def test_critical_risk_with_health_status_maps_to_health_alert_v2():
    opts = build_gate4_android_notification_options(
        risk="critical",
        priority="normal",
        category="health_status",
    )
    assert opts["channel_id"] == CHANNEL_HEALTH_ALERT_V2
    assert opts["critical"] is True
    assert opts["alarm_like"] is True


def test_reminder_maps_to_engagement_v2():
    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="reminder",
    )
    assert opts["channel_id"] == CHANNEL_ENGAGEMENT_V2
    assert opts["sound"] == CANONICAL_SEDI_SOUND
    assert opts["android_priority"] == "normal"


def test_reminder_with_high_priority_maps_to_health_alert_v2_by_precedence():
    high_priority = build_gate4_android_notification_options(
        risk="normal",
        priority="high",
        category="reminder",
    )
    assert high_priority["channel_id"] == CHANNEL_HEALTH_ALERT_V2
    assert high_priority["android_priority"] == "high"
    assert high_priority["critical"] is False

    high_risk = build_gate4_android_notification_options(
        risk="high",
        priority="normal",
        category="reminder",
    )
    assert high_risk["channel_id"] == CHANNEL_HEALTH_ALERT_V2


def test_default_maps_to_engagement_v2():
    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="engagement",
    )
    assert opts["channel_id"] == CHANNEL_ENGAGEMENT_V2
    assert opts["sound"] == CANONICAL_SEDI_SOUND
    assert opts["android_priority"] == "normal"


def test_morning_is_audible_on_morning_v3():
    from backend.app.services.gate4.push_payload import CHANNEL_MORNING_V3

    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="morning",
        sound_enabled=True,
    )
    assert opts["channel_id"] == CHANNEL_MORNING_V3
    assert opts["sound"] == CANONICAL_SEDI_SOUND
    assert opts["play_sound"] is True


def test_daily_status_is_audible_on_morning_v3():
    from backend.app.services.gate4.push_payload import CHANNEL_MORNING_V3

    opts = build_gate4_android_notification_options(
        risk="informational",
        priority="normal",
        category="daily_status",
        sound_enabled=True,
    )
    assert opts["channel_id"] == CHANNEL_MORNING_V3
    assert opts["sound"] == CANONICAL_SEDI_SOUND
    assert opts["play_sound"] is True


def test_normalize_invalid_language_falls_back_to_en():
    assert normalize_language("de") == "en"
    assert normalize_push_language("de") == "en"
    assert normalize_push_language("DE-de") == "en"
    assert normalize_push_language("unsupported-lang") == "en"
    assert "de" not in normalize_push_language("de")


def test_invalid_language_uses_english_canonical_action_labels():
    for action_id in (
        SmartNotificationAction.ACK_THANKS.value,
        SmartNotificationAction.NOT_NOW.value,
        SmartNotificationAction.TALK_LATER.value,
        SmartNotificationAction.OPEN_CHAT.value,
    ):
        label = get_action_label(action_id, "de")
        assert label == ACTION_LABELS[action_id]["en"]
        assert label != ACTION_LABELS[action_id]["fa"]
        assert label != ACTION_LABELS[action_id]["ar"]


def test_invalid_language_metadata_and_push_payload_fall_back_to_en():
    meta = build_smart_notification_metadata(
        notification_id=42,
        category="engagement",
        risk="normal",
        language="de",
        source_notification_id=42,
        deeplink_url="sedi://chat?from=notif&source_notification_id=42",
    )
    assert meta["language"] == "en"
    assert "de" not in meta["language"]
    for action in meta["actions"]:
        expected = ACTION_LABELS[action["action_id"]]["en"]
        assert action["label"] == expected

    payload = build_gate4_push_data_payload(
        notification_id=42,
        user_id=7,
        title="Title",
        body="Body",
        category="engagement",
        risk="normal",
        priority="normal",
        language="de",
        deeplink_url="sedi://chat?from=notif&source_notification_id=42",
        source_notification_id=42,
        actions=[
            SmartNotificationAction.ACK_THANKS.value,
            SmartNotificationAction.OPEN_CHAT.value,
        ],
    )
    assert payload["language"] == "en"
    assert payload["channel_id"] == CHANNEL_ENGAGEMENT_V2
    assert payload["sound"] == CANONICAL_SEDI_SOUND
    assert "de" not in payload.get("language", "")
    assert "de" not in payload.get("gate4_actions", "")
    for action_id, en_label in (
        (SmartNotificationAction.ACK_THANKS.value, ACTION_LABELS[SmartNotificationAction.ACK_THANKS.value]["en"]),
        (SmartNotificationAction.OPEN_CHAT.value, ACTION_LABELS[SmartNotificationAction.OPEN_CHAT.value]["en"]),
    ):
        assert en_label in payload["gate4_actions"]
        assert ACTION_LABELS[action_id]["fa"] not in payload["gate4_actions"]

def test_a4_mobile_interaction_labels_fa_en_ar():
    from backend.app.services.gate4.push_payload import MOBILE_INTERACTION_ACTIONS, build_gate4_push_data_payload

    for lang in ("fa", "en", "ar"):
        data = build_gate4_push_data_payload(
            notification_id=1,
            user_id=1,
            title="t",
            body="b",
            category="engagement",
            risk="normal",
            priority="normal",
            language=lang,
            deeplink_url="sedi://chat?from=notif",
            actions=list(MOBILE_INTERACTION_ACTIONS),
        )
        assert "like" in data["gate4_actions"]
        assert "dislike" in data["gate4_actions"]
        assert "open_chat" in data["gate4_actions"]
        assert data.get("play_sound") == "true"
