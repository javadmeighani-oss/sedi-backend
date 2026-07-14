"""Gate 4 Android channel routing unit tests (Section 14-A1 / Section 15-P1)."""

from __future__ import annotations

from backend.app.services.gate4.notification_contract import (
    ACTION_LABELS,
    SmartNotificationAction,
    build_smart_notification_metadata,
    get_action_label,
    normalize_language,
)
from backend.app.services.gate4.push_payload import (
    build_gate4_android_notification_options,
    build_gate4_push_data_payload,
    normalize_push_language,
)


def test_health_status_maps_to_sedi_health():
    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="health_status",
    )
    assert opts["channel_id"] == "sedi_health"
    assert opts["android_priority"] == "high"
    assert opts["critical"] is False


def test_health_alert_maps_to_sedi_health():
    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="health_alert",
    )
    assert opts["channel_id"] == "sedi_health"
    assert opts["android_priority"] == "high"


def test_critical_maps_to_sedi_critical():
    opts = build_gate4_android_notification_options(
        risk="critical",
        priority="critical",
        category="health_alert",
    )
    assert opts["channel_id"] == "sedi_critical"
    assert opts["android_priority"] == "high"
    assert opts["critical"] is True
    assert opts["alarm_like"] is True


def test_critical_risk_with_health_status_maps_to_sedi_critical():
    """Risk ``critical`` takes precedence over health_status category."""
    opts = build_gate4_android_notification_options(
        risk="critical",
        priority="normal",
        category="health_status",
    )
    assert opts["channel_id"] == "sedi_critical"
    assert opts["critical"] is True
    assert opts["alarm_like"] is True


def test_reminder_maps_to_sedi_reminder():
    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="reminder",
    )
    assert opts["channel_id"] == "sedi_reminder"
    assert opts["android_priority"] == "normal"


def test_reminder_with_high_priority_maps_to_sedi_health_by_precedence():
    """
    Documented implementation precedence (do not change without product approval):

    1. risk == critical → sedi_critical
    2. health category OR risk high OR priority high/critical → sedi_health
    3. reminder categories → sedi_reminder
    4. else → sedi_default

    Therefore a reminder with high priority/risk routes to ``sedi_health``,
    not ``sedi_reminder``.
    """
    high_priority = build_gate4_android_notification_options(
        risk="normal",
        priority="high",
        category="reminder",
    )
    assert high_priority["channel_id"] == "sedi_health"
    assert high_priority["android_priority"] == "high"
    assert high_priority["critical"] is False

    high_risk = build_gate4_android_notification_options(
        risk="high",
        priority="normal",
        category="reminder",
    )
    assert high_risk["channel_id"] == "sedi_health"


def test_default_maps_to_sedi_default():
    opts = build_gate4_android_notification_options(
        risk="normal",
        priority="normal",
        category="engagement",
    )
    assert opts["channel_id"] == "sedi_default"
    assert opts["android_priority"] == "normal"


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
    )
    assert payload["language"] == "en"
    assert "de" not in payload.get("language", "")
    assert "de" not in payload.get("gate4_actions", "")
    for action_id, en_label in (
        (SmartNotificationAction.ACK_THANKS.value, ACTION_LABELS[SmartNotificationAction.ACK_THANKS.value]["en"]),
        (SmartNotificationAction.OPEN_CHAT.value, ACTION_LABELS[SmartNotificationAction.OPEN_CHAT.value]["en"]),
    ):
        assert en_label in payload["gate4_actions"]
        assert ACTION_LABELS[action_id]["fa"] not in payload["gate4_actions"]
