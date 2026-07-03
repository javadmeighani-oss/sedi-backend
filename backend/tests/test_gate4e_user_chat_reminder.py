"""Gate 4E — user chat reminder tests (no DB for parse; DB for create)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.services.gate4.user_chat_reminder import (
    parse_chat_reminder_request,
)


def test_parse_english_tomorrow_reminder():
    result = parse_chat_reminder_request(
        "Tomorrow at 10 remind me to take my medication",
        now_utc=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        user_timezone="UTC",
    )
    assert result.is_reminder_request is True
    assert result.needs_clarification is False
    assert result.reminder_title
    assert result.scheduled_at_utc is not None


def test_parse_persian_reminder():
    result = parse_chat_reminder_request(
        "فردا ساعت ۱۰ یادم بنداز دارویم را بخورم",
        now_utc=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        user_timezone="Asia/Tehran",
    )
    assert result.is_reminder_request is True


def test_parse_vague_reminder_needs_clarification():
    result = parse_chat_reminder_request("remind me to call the doctor")
    assert result.is_reminder_request is True
    assert result.needs_clarification is True


def test_parse_non_reminder():
    result = parse_chat_reminder_request("How are you today?")
    assert result.is_reminder_request is False


def test_dosage_advice_blocked():
    result = parse_chat_reminder_request("remind me to increase my medication dose tomorrow at 9")
    assert result.needs_clarification is True
    assert "dosage" in (result.clarification_message or "").lower()
