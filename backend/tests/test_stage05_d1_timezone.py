"""Stage 05-D1: timezone is asked naturally in chat and adopted from the device (never overwritten)."""
from types import SimpleNamespace

import pytest

from backend.app.schemas.chat import SessionOpenRequest
from backend.app.services import chat_commands as cc
from backend.app.services.i8 import exercise_primary_path as ex
from backend.app.services.i8 import nutrition_primary_path as nu


@pytest.mark.parametrize(
    "text,expected",
    [
        ("وقت تهران", "Asia/Tehran"),
        ("به وقت دبی", "Asia/Dubai"),
        ("منطقه زمانی ایران", "Asia/Tehran"),
        ("Tehran time", "Asia/Tehran"),
        ("london time", "Europe/London"),
        ("وقت دکتر در تهران", None),
        ("من در تهران زندگی می‌کنم", None),
        ("", None),
        ("وقت تهران " + "x" * 60, None),
    ],
)
def test_spoken_timezone_alias(text, expected):
    assert cc._alias_timezone(text) == expected


def test_alias_command_persists_and_confirms(monkeypatch):
    saved = {}
    monkeypatch.setattr(cc, "_persist_profile_timezone", lambda db, uid, tz: saved.update(tz=tz))
    out = cc.detect_and_handle_user_settings_command(1, "وقت تهران", db=None, language="fa")
    assert saved["tz"] == "Asia/Tehran" and "Asia/Tehran" in out.assistant_message


def test_adopt_device_timezone_only_when_profile_empty(monkeypatch):
    row = SimpleNamespace(timezone=None)
    added, commits = [], []
    db = SimpleNamespace(add=added.append, commit=lambda: commits.append(1))
    monkeypatch.setattr(cc, "ensure_profile_core", lambda d, uid: row)
    assert cc.adopt_device_timezone(db, 1, "Asia/Tehran") is True and row.timezone == "Asia/Tehran"
    assert cc.adopt_device_timezone(db, 1, "Europe/London") is False and row.timezone == "Asia/Tehran"
    assert cc.adopt_device_timezone(db, 1, "Not/AZone") is False
    assert cc.adopt_device_timezone(db, 1, None) is False


def test_session_open_accepts_optional_timezone_and_stays_backward_compatible():
    assert SessionOpenRequest().timezone is None
    assert SessionOpenRequest(timezone="Asia/Tehran").timezone == "Asia/Tehran"


def test_timezone_required_message_tells_the_user_what_to_say():
    for table in (nu._USER_MESSAGES, ex._USER_MESSAGES):
        assert "وقت تهران" in table["fa"]["TIMEZONE_REQUIRED"]
        assert "Tehran time" in table["en"]["TIMEZONE_REQUIRED"]
        assert "در پروفایل لازم است" not in table["fa"]["TIMEZONE_REQUIRED"]
