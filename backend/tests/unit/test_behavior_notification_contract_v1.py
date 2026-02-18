"""
Contract-style test: Behavior Layer V1 companion_ping notification generation.
- Blocked during quiet hours: try_create_companion_ping_notification returns None when is_within_quiet_hours.
- Allowed when outside quiet hours and under budget: returns a Notification with type=companion_ping, deeplink from=notif&type=companion_ping.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


@pytest.fixture
def behavior_user_id(db):
    from sqlalchemy import text
    uid = 70003
    db.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, NOW())"
        ),
        {"id": uid, "name": "Notif Contract Test", "secret": "z", "lang": "fa"},
    )
    db.commit()
    return uid


def test_companion_ping_blocked_during_quiet_hours(db, behavior_user_id):
    """When is_within_quiet_hours is True, try_create_companion_ping_notification returns None."""
    from unittest.mock import patch
    from backend.app.behavior.service import try_create_companion_ping_notification

    with patch("backend.app.behavior.service.is_behavior_v1_enabled", return_value=True):
        with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=True):
            result = try_create_companion_ping_notification(
                db, behavior_user_id, lang="fa"
            )
    assert result is None


def test_companion_ping_allowed_outside_quiet_hours_under_budget(db, behavior_user_id):
    """When outside quiet hours and under daily budget, creates Notification with type=companion_ping and deeplink from=notif&type=companion_ping."""
    from unittest.mock import patch
    from backend.app.behavior.service import try_create_companion_ping_notification

    with patch("backend.app.behavior.service.is_behavior_v1_enabled", return_value=True):
        with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
            result = try_create_companion_ping_notification(
                db, behavior_user_id, lang="fa"
            )
    assert result is not None
    assert result.type == "companion_ping"
    assert "from=notif" in (result.deeplink_url or "")
    assert "type=companion_ping" in (result.deeplink_url or "")
    assert result.body
    assert result.title


def test_companion_ping_two_initiations_same_day_blocked(db, behavior_user_id):
    """Two initiations in the same (user-local) day: second is blocked by initiated_today even if daily_initiated_count is stale or >0."""
    from unittest.mock import patch
    from backend.app.behavior.service import (
        try_create_companion_ping_notification,
        get_or_create_profile,
    )

    with patch("backend.app.behavior.service.is_behavior_v1_enabled", return_value=True):
        with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
            first = try_create_companion_ping_notification(
                db, behavior_user_id, lang="fa"
            )
    assert first is not None

    # Second call same day must be blocked (initiated_today=true)
    with patch("backend.app.behavior.service.is_behavior_v1_enabled", return_value=True):
        with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
            second = try_create_companion_ping_notification(
                db, behavior_user_id, lang="fa"
            )
    assert second is None

    # Optional: simulate stale daily_initiated_count (e.g. manually set to 0); policy should still block via initiated_today
    profile = get_or_create_profile(db, behavior_user_id)
    profile.daily_initiated_count = 0
    db.commit()
    db.refresh(profile)
    with patch("backend.app.behavior.service.is_behavior_v1_enabled", return_value=True):
        with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
            third = try_create_companion_ping_notification(
                db, behavior_user_id, lang="fa"
            )
    assert third is None
