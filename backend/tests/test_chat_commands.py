# tests/test_chat_commands.py
"""
Pytest tests for Stage 16.6.5 - Chat commands for notification preferences.

Tests:
- timezone valid/invalid
- quiet hours parse valid/invalid
- disable quiet hours
"""

import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from backend.app.services.chat_commands import (
    detect_and_handle_user_settings_command,
    ChatResponseOverride,
    _validate_iana_timezone,
    _validate_hhmm,
)


# ---- Unit tests (no DB) ----

def test_validate_iana_timezone_valid():
    """Valid IANA timezones should pass."""
    assert _validate_iana_timezone("Asia/Tehran") is True
    assert _validate_iana_timezone("America/New_York") is True
    assert _validate_iana_timezone("Europe/London") is True


def test_validate_iana_timezone_invalid():
    """Invalid timezones should fail."""
    assert _validate_iana_timezone("") is False
    assert _validate_iana_timezone("NotATimezone") is False
    assert _validate_iana_timezone("Asia/Invalid_City_XYZ") is False


def test_validate_hhmm():
    """HH:MM format validation."""
    assert _validate_hhmm("22:00") is True
    assert _validate_hhmm("08:00") is True
    assert _validate_hhmm("00:00") is True
    assert _validate_hhmm("23:59") is True
    assert _validate_hhmm("9:30") is True
    assert _validate_hhmm("25:00") is False
    assert _validate_hhmm("12:60") is False
    assert _validate_hhmm("invalid") is False


# ---- Integration tests (with mocked DB) ----

def test_set_timezone_command_en():
    """English: set timezone Asia/Tehran -> stores and returns success."""
    db = MagicMock(spec=Session)
    repo_inst = MagicMock()
    with patch("backend.app.services.chat_commands.MemoryRepository", return_value=repo_inst):
        result = detect_and_handle_user_settings_command(
            user_id=1,
            text="set timezone Asia/Tehran",
            db=db,
            language="en",
        )
    assert result is not None
    assert isinstance(result, ChatResponseOverride)
    assert "Asia/Tehran" in result.assistant_message
    repo_inst.upsert_fact.assert_called_once()
    call_kw = repo_inst.upsert_fact.call_args[1]
    assert call_kw["domain"] == "preferences"
    assert call_kw["key"] == "timezone"
    assert call_kw["value"] == {"tz": "Asia/Tehran"}


def test_set_timezone_invalid_returns_message():
    """Invalid timezone -> returns error message, no upsert."""
    db = MagicMock(spec=Session)
    repo_inst = MagicMock()
    with patch("backend.app.services.chat_commands.MemoryRepository", return_value=repo_inst):
        result = detect_and_handle_user_settings_command(
            user_id=1,
            text="set timezone NotATimezone",
            db=db,
            language="en",
        )
    assert result is not None
    assert "not valid" in result.assistant_message.lower() or "invalid" in result.assistant_message.lower()
    repo_inst.upsert_fact.assert_not_called()


def test_set_quiet_hours_command():
    """quiet hours 22:00-08:00 -> stores and returns success."""
    db = MagicMock(spec=Session)
    repo_inst = MagicMock()
    with patch("backend.app.services.chat_commands.MemoryRepository", return_value=repo_inst):
        result = detect_and_handle_user_settings_command(
            user_id=1,
            text="quiet hours 22:00-08:00",
            db=db,
            language="en",
        )
    assert result is not None
    assert "22:00" in result.assistant_message or "08:00" in result.assistant_message
    repo_inst.upsert_fact.assert_called_once()
    call_kw = repo_inst.upsert_fact.call_args[1]
    assert call_kw["key"] == "quiet_hours"
    assert call_kw["value"]["enabled"] is True
    assert call_kw["value"]["start"] == "22:00"
    assert call_kw["value"]["end"] == "08:00"


def test_disable_quiet_hours_command():
    """disable quiet hours -> stores enabled=False."""
    db = MagicMock(spec=Session)
    repo_inst = MagicMock()
    with patch("backend.app.services.chat_commands.MemoryRepository", return_value=repo_inst):
        result = detect_and_handle_user_settings_command(
            user_id=1,
            text="disable quiet hours",
            db=db,
            language="en",
        )
    assert result is not None
    assert "disabled" in result.assistant_message.lower()
    repo_inst.upsert_fact.assert_called_once()
    call_kw = repo_inst.upsert_fact.call_args[1]
    assert call_kw["key"] == "quiet_hours"
    assert call_kw["value"]["enabled"] is False


def test_normal_message_returns_none():
    """Normal chat message -> returns None (no command)."""
    db = MagicMock(spec=Session)
    result = detect_and_handle_user_settings_command(
        user_id=1,
        text="How are you today?",
        db=db,
        language="en",
    )
    assert result is None


def test_persian_timezone_command():
    """Persian: تایم زون: Asia/Tehran -> stores."""
    db = MagicMock(spec=Session)
    repo_inst = MagicMock()
    with patch("backend.app.services.chat_commands.MemoryRepository", return_value=repo_inst):
        result = detect_and_handle_user_settings_command(
            user_id=1,
            text="تایم زون: Asia/Tehran",
            db=db,
            language="fa",
        )
    assert result is not None
    assert "Asia/Tehran" in result.assistant_message
    repo_inst.upsert_fact.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
