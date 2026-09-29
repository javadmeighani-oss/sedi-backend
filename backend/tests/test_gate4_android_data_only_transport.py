"""Gate4 Android FCM transport: data-only single-render contract."""

from __future__ import annotations

from backend.app.services.notifications.fcm_client import (
    _build_fcm_message,
    _is_gate4_actionable_android,
)


def test_gate4_android_data_only_no_system_notification_envelope():
    data = {
        "gate": "gate4",
        "gate4_actions": '[{"action_id":"like","label":"Like"}]',
        "channel_id": "morning_v3",
        "title": "Morning",
        "body": "Hello from Sedi",
        "notification_id": "42",
        "play_sound": "true",
        "sound": "sedi_alarm",
    }
    assert _is_gate4_actionable_android(data) is True
    msg = _build_fcm_message(
        token="tok",
        title="Morning",
        body="Hello from Sedi",
        data=data,
        android_priority="normal",
    )["message"]
    assert "notification" not in msg
    assert "notification" not in msg.get("android", {})
    assert msg["data"]["title"] == "Morning"
    assert msg["data"]["body"] == "Hello from Sedi"
    assert msg["data"]["channel_id"] == "morning_v3"
    assert msg["android"]["priority"] == "high"


def test_legacy_non_gate4_keeps_notification_envelope():
    data = {
        "notification_id": "7",
        "channel": "engagement",
        "channel_id": "engagement_v2",
        "play_sound": "true",
        "sound": "sedi_alarm",
    }
    assert _is_gate4_actionable_android(data) is False
    msg = _build_fcm_message(
        token="tok",
        title="Ping",
        body="Legacy body",
        data=data,
        android_priority="normal",
    )["message"]
    assert msg["notification"]["title"] == "Ping"
    assert msg["notification"]["body"] == "Legacy body"
    assert msg["android"]["notification"]["channel_id"] == "engagement_v2"
    assert msg["android"]["notification"]["sound"] == "sedi_alarm"
    assert msg["android"]["priority"] == "normal"


def test_a3_session_open_arabic_brand_is_sedi_fa_form():
    from backend.app.models import User
    from backend.app.services.a3_session_open import build_first_intro_message

    u = User(name="Ali", secret_key="t", preferred_language="ar")
    msg = build_first_intro_message(u)
    assert "صدی" in msg
    assert "صدي" not in msg
