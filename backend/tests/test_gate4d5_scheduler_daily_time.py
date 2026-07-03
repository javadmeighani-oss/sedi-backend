"""Gate 4D-5 — scheduler daily time / local timezone integration tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.models import Notification, NotificationPrefs, User, UserMemoryFact, UserProfileCore
from backend.app.services.gate4.feature_flags import gate4_daily_0800_enabled
from backend.app.services.gate4.notification_policy import DEFAULT_DAILY_NOTIFICATION_TIME
from backend.app.services.gate4.scheduler_timing import (
    GATE4_DAILY_TOLERANCE_MINUTES,
    legacy_should_run_morning_notification,
    resolve_user_daily_notification_time_for_scheduler,
    resolve_user_timezone_for_scheduler,
    should_run_daily_notification_gate4,
)
from backend.app.services.memory import MemoryRepository


@pytest.fixture(autouse=True)
def _clear_gate4_daily_flag(monkeypatch):
    monkeypatch.delenv("SEDI_GATE4_DAILY_0800_ENABLED", raising=False)


def test_feature_flag_default_false():
    assert gate4_daily_0800_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", " Yes ", "ON"])
def test_feature_flag_parses_true_values(monkeypatch, value):
    monkeypatch.setenv("SEDI_GATE4_DAILY_0800_ENABLED", value)
    assert gate4_daily_0800_enabled() is True


@pytest.fixture
def sched_user(db):
    user = User(name="Scheduler User", secret_key="d5", preferred_language="en")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_flags_off_legacy_path_differs_from_gate4_default_at_0800(db, sched_user):
    """Legacy default is 09:00; Gate 4 default is 08:00 — same instant, different outcomes."""
    # 08:05 Asia/Tehran ≈ 04:35 UTC
    now_utc = datetime(2026, 7, 2, 4, 35, tzinfo=timezone.utc)
    memory_repo = MemoryRepository(db)

    assert legacy_should_run_morning_notification(memory_repo, sched_user, now_utc) is False
    assert should_run_daily_notification_gate4(db, sched_user, now_utc) is True


def test_gate4_daily_time_fallback_08_00_without_prefs_or_memory(db, sched_user):
    assert resolve_user_daily_notification_time_for_scheduler(db, sched_user) == "08:00"
    assert DEFAULT_DAILY_NOTIFICATION_TIME == "08:00"


def test_gate4_daily_time_uses_prefs(db, sched_user):
    db.add(
        NotificationPrefs(
            user_id=sched_user.id,
            daily_notification_time="09:30",
        )
    )
    db.commit()
    assert resolve_user_daily_notification_time_for_scheduler(db, sched_user) == "09:30"


def test_gate4_daily_time_uses_memory_when_no_prefs(db, sched_user):
    db.add(
        UserMemoryFact(
            user_id=sched_user.id,
            domain="preferences",
            key="morning_notification_time",
            value_json='{"hour": 7, "minute": 15}',
            confidence=0.9,
            source="manual",
        )
    )
    db.commit()
    assert resolve_user_daily_notification_time_for_scheduler(db, sched_user) == "07:15"


def test_prefs_daily_time_preferred_over_memory(db, sched_user):
    db.add(
        NotificationPrefs(user_id=sched_user.id, daily_notification_time="10:00")
    )
    db.add(
        UserMemoryFact(
            user_id=sched_user.id,
            domain="preferences",
            key="morning_notification_time",
            value_json='{"hour": 7, "minute": 0}',
            confidence=0.9,
            source="manual",
        )
    )
    db.commit()
    assert resolve_user_daily_notification_time_for_scheduler(db, sched_user) == "10:00"


def test_timezone_prefers_user_profile_core(db, sched_user):
    db.add(UserProfileCore(user_id=sched_user.id, timezone="Europe/London"))
    db.commit()
    assert resolve_user_timezone_for_scheduler(db, sched_user) == "Europe/London"


def test_timezone_falls_back_to_memory_fact(db, sched_user):
    db.add(
        UserMemoryFact(
            user_id=sched_user.id,
            domain="preferences",
            key="timezone",
            value_json='{"tz": "America/New_York"}',
            confidence=0.9,
            source="manual",
        )
    )
    db.commit()
    assert resolve_user_timezone_for_scheduler(db, sched_user) == "America/New_York"


def test_timezone_final_fallback_tehran(db, sched_user):
    assert resolve_user_timezone_for_scheduler(db, sched_user) == "Asia/Tehran"


def test_should_run_true_within_tolerance(db, sched_user):
    db.add(UserProfileCore(user_id=sched_user.id, timezone="Asia/Tehran"))
    db.commit()
    # 08:05 Tehran = 04:35 UTC
    now_utc = datetime(2026, 7, 2, 4, 35, tzinfo=timezone.utc)
    assert should_run_daily_notification_gate4(db, sched_user, now_utc) is True


def test_should_run_false_outside_tolerance(db, sched_user):
    db.add(UserProfileCore(user_id=sched_user.id, timezone="Asia/Tehran"))
    db.commit()
    # 08:15 Tehran = 04:45 UTC (outside 10-minute window from 08:00)
    now_utc = datetime(2026, 7, 2, 4, 45, tzinfo=timezone.utc)
    assert should_run_daily_notification_gate4(db, sched_user, now_utc) is False


def test_invalid_prefs_time_falls_back_safely(db, sched_user):
    db.add(
        NotificationPrefs(
            user_id=sched_user.id,
            daily_notification_time="99:99",
        )
    )
    db.commit()
    # parse_hhmm falls back through chain to 08:00
    resolved = resolve_user_daily_notification_time_for_scheduler(db, sched_user)
    assert resolved == "08:00"


def test_invalid_timezone_falls_back_safely(db, sched_user):
    db.add(UserProfileCore(user_id=sched_user.id, timezone="Not/AZone"))
    db.commit()
    assert resolve_user_timezone_for_scheduler(db, sched_user) == "Asia/Tehran"


def test_helpers_do_not_commit_db(db, sched_user, monkeypatch):
    commit_calls: list[bool] = []

    def track_commit():
        commit_calls.append(True)

    monkeypatch.setattr(db, "commit", track_commit)

    resolve_user_daily_notification_time_for_scheduler(db, sched_user)
    resolve_user_timezone_for_scheduler(db, sched_user)
    should_run_daily_notification_gate4(
        db, sched_user, datetime(2026, 7, 2, 4, 35, tzinfo=timezone.utc)
    )
    assert commit_calls == []


def test_scheduler_uses_gate4_path_when_flag_on(db, sched_user, monkeypatch):
    monkeypatch.setenv("SEDI_GATE4_DAILY_0800_ENABLED", "true")

    with patch(
        "backend.app.services.gate4.scheduler_timing.should_run_daily_notification_gate4",
        return_value=False,
    ) as mock_gate4:
        with patch("backend.app.core.scheduler.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db])
            db.query(User).all = MagicMock(return_value=[sched_user])
            from backend.app.core.scheduler import run_morning_notifications

            run_morning_notifications()
            mock_gate4.assert_called_once()


def test_scheduler_uses_legacy_path_when_flag_off(db, sched_user, monkeypatch):
    with patch(
        "backend.app.services.gate4.scheduler_timing.should_run_daily_notification_gate4"
    ) as mock_gate4:
        with patch("backend.app.core.scheduler.get_db") as mock_get_db:
            mock_get_db.return_value = iter([db])
            db.query(User).all = MagicMock(return_value=[])
            from backend.app.core.scheduler import run_morning_notifications

            run_morning_notifications()
            mock_gate4.assert_not_called()


def test_morning_dedupe_prevents_second_brief_same_day(db, sched_user):
    """Existing dedupe: one morning_brief per user per UTC calendar day in scheduler."""
    today = datetime(2026, 7, 2, 5, 0, 0)
    db.add(
        Notification(
            user_id=sched_user.id,
            type="morning_brief",
            title="Morning",
            body="Already sent",
            priority="normal",
            is_sent=False,
            created_at=today,
            dedupe_key=f"morning_brief:{sched_user.id}:2026-07-02",
        )
    )
    db.commit()

    today_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id == sched_user.id,
            Notification.type == "morning_brief",
            Notification.created_at >= today_start,
        )
        .count()
    )
    assert existing == 1


def test_tolerance_matches_scheduler_interval():
    assert GATE4_DAILY_TOLERANCE_MINUTES == 10
