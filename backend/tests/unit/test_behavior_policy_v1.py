"""
Unit tests: Behavior Layer V1 policy.
- Quiet hours block: can_initiate returns (False, "quiet_hours") when within quiet hours.
- Daily cap block: can_initiate returns (False, "daily_cap") when daily_initiated_count >= budget.
- Cooldown block: can_initiate returns (False, "cooldown") when last_initiated within cooldown window.
- Mode selection: score_to_mode / mode_from_score mapping (low / normal / high).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from backend.app.behavior.models import BehaviorMode, score_to_mode
from backend.app.behavior.policy import BehaviorPolicy


# --- Mode selection: score -> mode mapping ---

def test_score_to_mode_low():
    """Score < 0.3 => low."""
    assert score_to_mode(0.0) == BehaviorMode.low
    assert score_to_mode(0.29) == BehaviorMode.low


def test_score_to_mode_normal():
    """0.3 <= score < 0.7 => normal."""
    assert score_to_mode(0.3) == BehaviorMode.normal
    assert score_to_mode(0.5) == BehaviorMode.normal
    assert score_to_mode(0.69) == BehaviorMode.normal


def test_score_to_mode_high():
    """Score >= 0.7 => high."""
    assert score_to_mode(0.7) == BehaviorMode.high
    assert score_to_mode(1.0) == BehaviorMode.high


def test_policy_mode_from_score():
    """BehaviorPolicy.mode_from_score uses same mapping."""
    policy = BehaviorPolicy(daily_budget=3, cooldown_minutes=60)
    assert policy.mode_from_score(0.2) == BehaviorMode.low
    assert policy.mode_from_score(0.5) == BehaviorMode.normal
    assert policy.mode_from_score(0.8) == BehaviorMode.high


# --- should_add_lead_in ---

def test_should_add_lead_in_low_never():
    """Mode low => never add lead-in."""
    policy = BehaviorPolicy()
    assert policy.should_add_lead_in(BehaviorMode.low, "confirm_candidate") is False
    assert policy.should_add_lead_in(BehaviorMode.low, "profile_question") is False


def test_should_add_lead_in_high_always():
    """Mode high => always add lead-in."""
    policy = BehaviorPolicy()
    assert policy.should_add_lead_in(BehaviorMode.high, "confirm_candidate") is True
    assert policy.should_add_lead_in(BehaviorMode.high, "profile_question") is True


def test_should_add_lead_in_normal_only_confirm():
    """Mode normal => add lead-in only for confirm_candidate."""
    policy = BehaviorPolicy()
    assert policy.should_add_lead_in(BehaviorMode.normal, "confirm_candidate") is True
    assert policy.should_add_lead_in(BehaviorMode.normal, "profile_question") is False


# --- can_initiate: initiated_today block ---

def test_can_initiate_initiated_today_block(db, behavior_user_id):
    """When initiated_today=True, can_initiate returns (False, 'initiated_today') regardless of daily_initiated_count."""
    from unittest.mock import patch
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
        policy = BehaviorPolicy(daily_budget=3, cooldown_minutes=60)
        allowed, reason = policy.can_initiate(
            db, behavior_user_id, datetime.utcnow(),
            daily_initiated_count=0,
            last_initiated_at=None,
            initiated_today=True,
        )
        assert allowed is False
        assert reason == "initiated_today"
        # Stale count > 0 still blocked by initiated_today
        allowed2, reason2 = policy.can_initiate(
            db, behavior_user_id, datetime.utcnow(),
            daily_initiated_count=5,
            last_initiated_at=None,
            initiated_today=True,
        )
        assert allowed2 is False
        assert reason2 == "initiated_today"


# --- can_initiate: daily cap block ---

def test_can_initiate_daily_cap_block(db, behavior_user_id):
    """When daily_initiated_count >= daily_budget, can_initiate returns (False, 'daily_cap')."""
    from unittest.mock import patch
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
        policy = BehaviorPolicy(daily_budget=2, cooldown_minutes=60)
        allowed, reason = policy.can_initiate(
            db, behavior_user_id, datetime.utcnow(),
            daily_initiated_count=2,
            last_initiated_at=None,
        )
        assert allowed is False
        assert reason == "daily_cap"


# --- can_initiate: cooldown block ---

def test_can_initiate_cooldown_block(db, behavior_user_id):
    """When last_initiated_at within cooldown window, can_initiate returns (False, 'cooldown')."""
    from unittest.mock import patch
    now = datetime.utcnow()
    one_minute_ago = now - timedelta(minutes=1)
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
        policy = BehaviorPolicy(daily_budget=3, cooldown_minutes=60)
        allowed, reason = policy.can_initiate(
            db, behavior_user_id, now,
            daily_initiated_count=0,
            last_initiated_at=one_minute_ago,
        )
        assert allowed is False
        assert reason == "cooldown"


# --- can_initiate: quiet hours block ---

def test_can_initiate_quiet_hours_block(db, behavior_user_id):
    """When is_within_quiet_hours returns True, can_initiate returns (False, 'quiet_hours')."""
    from unittest.mock import patch
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=True):
        policy = BehaviorPolicy(daily_budget=3, cooldown_minutes=60)
        allowed, reason = policy.can_initiate(
            db, behavior_user_id, datetime.utcnow(),
            daily_initiated_count=0,
            last_initiated_at=None,
        )
        assert allowed is False
        assert reason == "quiet_hours"


# --- can_initiate: allowed ---

def test_can_initiate_allowed(db, behavior_user_id):
    """When under cap, past cooldown, and not quiet hours, can_initiate returns (True, '')."""
    from unittest.mock import patch
    now = datetime.utcnow()
    two_hours_ago = now - timedelta(hours=2)
    with patch("backend.app.behavior.policy.is_within_quiet_hours", return_value=False):
        policy = BehaviorPolicy(daily_budget=3, cooldown_minutes=60)
        allowed, reason = policy.can_initiate(
            db, behavior_user_id, now,
            daily_initiated_count=0,
            last_initiated_at=two_hours_ago,
        )
        assert allowed is True
        assert reason == ""


@pytest.fixture
def behavior_user_id(db):
    """Insert a user for behavior tests."""
    from sqlalchemy import text
    uid = 70001
    db.execute(
        text(
            "INSERT INTO users (id, name, secret_key, preferred_language, created_at) "
            "VALUES (:id, :name, :secret, :lang, NOW())"
        ),
        {"id": uid, "name": "Behavior Test", "secret": "x", "lang": "fa"},
    )
    db.commit()
    return uid
